"""Компрехенсивный аудит Kontur vs AeroBIM (audit-2026-09). 13 находок, 17 тестов."""

from __future__ import annotations

import asyncio
import time
import warnings

import pytest
from fastapi.testclient import TestClient

from kontur.domain.capabilities import (
    CapStatus, Capability, engine_health_summary,
    kit_blocked, kit_degraded, overall_kit_status,
)
from kontur.domain.models import Finding
from kontur.domain.statuses import DisagreementKind, FindingStatus, ReviewPriority
from kontur.infrastructure.pdf_guard import PdfParseTimeoutError, parse_with_timeout
from kontur.presentation.api import app


def _make_finding(**kwargs: object) -> Finding:
    defaults: dict[str, object] = dict(
        finding_id="f-001", rule_code="IOS4-078",
        finding_status=FindingStatus.MISSING_EVIDENCE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="1.0", rule_version="1.0", model_version="0.1",
    )
    defaults.update(kwargs)
    return Finding(**defaults)  # type: ignore[arg-type]


# --- Finding #1: kit_degraded ---

class TestKitDegraded:
    def test_all_available_not_degraded(self) -> None:
        caps = (Capability("vector_text", CapStatus.AVAILABLE, True), Capability("ocr_text", CapStatus.AVAILABLE, True))
        assert not kit_degraded(caps)

    def test_verdict_degraded_detected(self) -> None:
        caps = (Capability("vector_text", CapStatus.AVAILABLE, True), Capability("ocr_text", CapStatus.DEGRADED, True))
        assert kit_degraded(caps)

    def test_advisory_degraded_ignored(self) -> None:
        caps = (Capability("vector_text", CapStatus.AVAILABLE, True), Capability("llm_advisory", CapStatus.DEGRADED, False))
        assert not kit_degraded(caps)

    def test_unavailable_is_blocked_not_degraded(self) -> None:
        caps = (Capability("vector_text", CapStatus.UNAVAILABLE, True),)
        assert kit_blocked(caps) and not kit_degraded(caps)


# --- Finding #2: DisagreementKind ---

class TestDisagreementKind:
    def test_all_four_values(self) -> None:
        assert {k.value for k in DisagreementKind} == {"VALUE_DELTA", "MISSING_IN_STAGE", "AMBIGUOUS_REFERENCE", "FORMAT_MISMATCH"}

    def test_ios4_078_value_delta(self) -> None:
        assert DisagreementKind.VALUE_DELTA == "VALUE_DELTA"


# --- Findings #3, #4, #5: Finding provenance ---

class TestFindingProvenance:
    def test_source_id_stored(self) -> None:
        assert _make_finding(source_id="pd:p12:frag-abc").source_id == "pd:p12:frag-abc"

    def test_evidence_refs_stored(self) -> None:
        assert _make_finding(evidence_refs=("frag-1", "frag-2")).evidence_refs == ("frag-1", "frag-2")

    def test_disagreement_kind_stored(self) -> None:
        assert _make_finding(disagreement_kind=DisagreementKind.VALUE_DELTA).disagreement_kind is DisagreementKind.VALUE_DELTA

    def test_has_provenance_true(self) -> None:
        assert _make_finding(source_id="pd:p1:x", evidence_refs=("x",)).has_provenance

    def test_has_provenance_false_without_source_id(self) -> None:
        assert not _make_finding(evidence_refs=("x",)).has_provenance

    def test_soft_warning_when_group_id_without_source_id(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _make_finding(finding_id="f-w", finding_status=FindingStatus.CANDIDATE, evidence_group_id="eg-001", source_id=None)
        user = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(user) == 1 and "source_id" in str(user[0].message)

    def test_no_warning_when_source_id_present(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _make_finding(finding_id="f-ok", finding_status=FindingStatus.CANDIDATE, evidence_group_id="eg-001", source_id="pd:p1:x")
        assert not [x for x in w if issubclass(x.category, UserWarning)]


# --- Findings #6, #7, #8: pdf_guard ---

class TestPdfGuard:
    def test_error_carries_process_id(self) -> None:
        err = PdfParseTimeoutError(process_id="proc-abc", timeout_s=5.0)
        assert err.process_id == "proc-abc" and "proc-abc" in str(err)

    def test_disabled_when_zero(self) -> None:
        assert asyncio.run(parse_with_timeout(lambda: "ok", timeout_s=0)) == "ok"

    def test_fast_callable(self) -> None:
        assert asyncio.run(parse_with_timeout(lambda: 42, timeout_s=5.0)) == 42

    def test_slow_callable_raises(self) -> None:
        async def _run() -> None:
            await parse_with_timeout(lambda: time.sleep(10), timeout_s=0.05, process_id="p-slow")
        with pytest.raises(PdfParseTimeoutError) as exc_info:
            asyncio.run(_run())
        assert exc_info.value.process_id == "p-slow"

    def test_exception_propagates(self) -> None:
        async def _run() -> None:
            await parse_with_timeout(lambda: (_ for _ in ()).throw(ValueError("corrupt pdf")), timeout_s=5.0)
        with pytest.raises(ValueError, match="corrupt pdf"):
            asyncio.run(_run())


# --- Findings #9, #10: engine_health_summary ---

class TestEngineHealthSummary:
    def test_available_ok(self) -> None:
        assert engine_health_summary((Capability("vector_text", CapStatus.AVAILABLE, True),))["vector_text"] == "ok"

    def test_degraded(self) -> None:
        assert engine_health_summary((Capability("ocr_text", CapStatus.DEGRADED, True),))["ocr_text"] == "degraded"

    def test_advisory_unavailable_skipped(self) -> None:
        assert engine_health_summary((Capability("llm_advisory", CapStatus.UNAVAILABLE, False),))["llm_advisory"] == "skipped"

    def test_verdict_unavailable_failed(self) -> None:
        assert engine_health_summary((Capability("ocr_tables", CapStatus.UNAVAILABLE, True),))["ocr_tables"] == "failed"


# --- Findings #11, #12: overall_kit_status ---

class TestOverallKitStatus:
    def test_all_ok(self) -> None:
        assert overall_kit_status((Capability("v", CapStatus.AVAILABLE, True), Capability("a", CapStatus.AVAILABLE, False))) == "OK"

    def test_verdict_unavailable_blocked(self) -> None:
        assert overall_kit_status((Capability("ocr_text", CapStatus.UNAVAILABLE, True),)) == "BLOCKED"

    def test_verdict_degraded(self) -> None:
        assert overall_kit_status((Capability("drawing_analysis", CapStatus.DEGRADED, True),)) == "DEGRADED"

    def test_advisory_unavailable_still_ok(self) -> None:
        caps = (Capability("v", CapStatus.AVAILABLE, True), Capability("llm_advisory", CapStatus.UNAVAILABLE, False))
        assert overall_kit_status(caps) == "OK"


# --- Finding #13: GET /api/v1/system/capabilities ---

class TestCapabilitiesEndpoint:
    def setup_method(self) -> None:
        self.client = TestClient(app)

    def test_returns_200(self) -> None:
        assert self.client.get("/api/v1/system/capabilities").status_code == 200

    def test_required_keys(self) -> None:
        body = self.client.get("/api/v1/system/capabilities").json()
        for key in ("overall_kit_status", "engine_status", "affected_verdict_engines"):
            assert key in body

    def test_default_all_ok(self) -> None:
        body = self.client.get("/api/v1/system/capabilities").json()
        assert body["overall_kit_status"] == "OK"
        assert all(v == "ok" for v in body["engine_status"].values())
        assert body["affected_verdict_engines"] == []

    def test_degraded_reflected(self) -> None:
        degraded = (
            Capability("vector_text", CapStatus.AVAILABLE, True),
            Capability("ocr_text", CapStatus.DEGRADED, True),
            Capability("ocr_tables", CapStatus.AVAILABLE, True),
            Capability("drawing_analysis", CapStatus.AVAILABLE, True),
            Capability("llm_advisory", CapStatus.AVAILABLE, False),
        )
        app.state.capabilities = degraded
        try:
            body = self.client.get("/api/v1/system/capabilities").json()
            assert body["overall_kit_status"] == "DEGRADED"
            assert body["engine_status"]["ocr_text"] == "degraded"
            assert "ocr_text" in body["affected_verdict_engines"]
        finally:
            app.state.capabilities = None
