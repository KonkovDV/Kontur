"""Red Team фактчекинг аудита 2026-09.

Проверяет реальные интерфейсы main (4c1c518), а не предполагаемые.

Находки PR #36 (Red Team Findings):
  RT-1  engine_health_summary возвращает {healthy,degraded,failed,skipped: list[str]}
  RT-2  /capabilities отвечает {overall, kit_blocked, engines, health, note}
  RT-3  /capabilities требует auth token (401 без)
  RT-4  pdf_guard: run_pdf_parse_sync/run_pdf_parse, нет process_id, 0 райзит ValueError
  RT-5  overall_kit_status возвращает CapStatus (AVAILABLE/DEGRADED/UNAVAILABLE)
  RT-6  Finding не издаёт UserWarning (нет в коде)
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.capabilities import (
    CapStatus,
    Capability,
    describe,
    engine_health_summary,
    kit_blocked,
    kit_degraded,
    overall_kit_status,
)
from kontur.domain.models import Finding
from kontur.domain.statuses import DisagreementKind, FindingStatus, ReviewPriority
from kontur.infrastructure.pdf_guard import (
    PdfParseTimeoutError,
    run_pdf_parse,
    run_pdf_parse_sync,
)
from kontur.presentation.api import app

INSPECTOR = {"Authorization": "Bearer insp-7/INSPECTOR"}


# ---------------------------------------------------------------------------
# Сетап клиента
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    app.state.workspace = ProcessWorkspace()
    return TestClient(app)


# ---------------------------------------------------------------------------
# RT-1: engine_health_summary возвращает {healthy: [...], degraded: [...], ...}
# ---------------------------------------------------------------------------

class TestEngineHealthSummaryActualAPI:
    """RT-1: API возвращает списки, не плоский словарь {name: label}."""

    def test_available_engine_in_healthy_list(self) -> None:
        caps = (describe("vector_text", CapStatus.AVAILABLE),)
        summary = engine_health_summary(caps)
        # RT-1: ключи — healthy/degraded/failed/skipped, не имена движков
        assert "healthy" in summary
        assert "degraded" in summary
        assert "failed" in summary
        assert "skipped" in summary
        assert "vector_text" in summary["healthy"]

    def test_degraded_verdict_engine_in_degraded_list(self) -> None:
        caps = (describe("ocr_text", CapStatus.DEGRADED),)
        assert "ocr_text" in engine_health_summary(caps)["degraded"]

    def test_advisory_unavailable_goes_to_skipped_not_failed(self) -> None:
        caps = (describe("llm_advisory", CapStatus.UNAVAILABLE),)
        summary = engine_health_summary(caps)
        assert "llm_advisory" in summary["skipped"]
        assert "llm_advisory" not in summary["failed"]

    def test_verdict_unavailable_goes_to_failed(self) -> None:
        caps = (describe("ocr_tables", CapStatus.UNAVAILABLE),)
        assert "ocr_tables" in engine_health_summary(caps)["failed"]

    def test_unmentioned_engines_go_to_skipped(self) -> None:
        caps = (describe("vector_text", CapStatus.AVAILABLE),)
        summary = engine_health_summary(caps)
        # OCR/чертёж не переданы — skipped, не healthy
        assert "ocr_text" in summary["skipped"]
        assert "drawing_analysis" in summary["skipped"]
        assert "ocr_text" not in summary["healthy"]

    def test_summary_never_invents_healthy_engines(self) -> None:
        """Capability honesty: невидимый движок не считается healthy."""
        caps = (describe("vector_text", CapStatus.AVAILABLE),)
        summary = engine_health_summary(caps)
        assert "ocr_text" not in summary["healthy"]
        assert "drawing_analysis" not in summary["healthy"]
        assert "llm_advisory" not in summary["healthy"]


# ---------------------------------------------------------------------------
# RT-5: overall_kit_status возвращает CapStatus, не str "BLOCKED"/"OK"
# ---------------------------------------------------------------------------

class TestOverallKitStatusActualAPI:
    """RT-5: возвращает CapStatus (StrEnum: AVAILABLE / DEGRADED / UNAVAILABLE).
    'BLOCKED' и 'OK' — не значения CapStatus.
    """

    def test_all_available_returns_capstatus_available(self) -> None:
        caps = (
            describe("vector_text", CapStatus.AVAILABLE),
            describe("llm_advisory", CapStatus.AVAILABLE),
        )
        result = overall_kit_status(caps)
        assert result is CapStatus.AVAILABLE
        assert result == "AVAILABLE"  # StrEnum работает

    def test_verdict_unavailable_returns_capstatus_unavailable(self) -> None:
        caps = (describe("ocr_text", CapStatus.UNAVAILABLE),)
        result = overall_kit_status(caps)
        assert result is CapStatus.UNAVAILABLE
        assert result == "UNAVAILABLE"  # RT-5: не 'BLOCKED'

    def test_verdict_degraded_returns_capstatus_degraded(self) -> None:
        caps = (describe("drawing_analysis", CapStatus.DEGRADED),)
        result = overall_kit_status(caps)
        assert result is CapStatus.DEGRADED
        assert result == "DEGRADED"

    def test_advisory_unavailable_does_not_raise_kit_unavailable(self) -> None:
        """ADR-003: advisory failure не влияет на kit status."""
        caps = (
            describe("vector_text", CapStatus.AVAILABLE),
            describe("llm_advisory", CapStatus.UNAVAILABLE),
        )
        assert overall_kit_status(caps) is CapStatus.AVAILABLE

    def test_kit_degraded_true_only_for_verdict_layer(self) -> None:
        caps_verdict = (describe("ocr_text", CapStatus.DEGRADED),)
        caps_advisory = (describe("llm_advisory", CapStatus.DEGRADED),)
        assert kit_degraded(caps_verdict) is True
        assert kit_degraded(caps_advisory) is False  # advisory не влияет

    def test_kit_blocked_false_for_advisory_down(self) -> None:
        caps = (
            describe("vector_text", CapStatus.AVAILABLE),
            describe("llm_advisory", CapStatus.UNAVAILABLE),
        )
        assert kit_blocked(caps) is False


# ---------------------------------------------------------------------------
# RT-2 + RT-3: /api/v1/system/capabilities формат ответа + auth
# ---------------------------------------------------------------------------

class TestCapabilitiesEndpointActualShape:
    """RT-2+RT-3: endpoint требует auth и возвращает capabilities_payload() формат."""

    def setup_method(self) -> None:
        app.state.workspace = ProcessWorkspace()
        self.client = TestClient(app)

    def test_no_token_returns_401(self) -> None:
        # RT-3: endpoint требует token
        assert self.client.get("/api/v1/system/capabilities").status_code == 401

    def test_with_inspector_token_returns_200(self) -> None:
        assert (
            self.client.get("/api/v1/system/capabilities", headers=INSPECTOR).status_code == 200
        )

    def test_response_has_correct_top_level_keys(self) -> None:
        # RT-2: ключи — overall/kit_blocked/engines/health, не overall_kit_status/engine_status
        body = self.client.get("/api/v1/system/capabilities", headers=INSPECTOR).json()
        assert "overall" in body
        assert "kit_blocked" in body
        assert "engines" in body
        assert "health" in body
        # Отсутствующие ключи PR #36
        assert "overall_kit_status" not in body
        assert "engine_status" not in body
        assert "affected_verdict_engines" not in body

    def test_overall_is_available_because_vector_is_live(self) -> None:
        body = self.client.get("/api/v1/system/capabilities", headers=INSPECTOR).json()
        assert body["overall"] == "AVAILABLE"
        assert body["kit_blocked"] is False

    def test_engines_list_contains_engine_objects(self) -> None:
        body = self.client.get("/api/v1/system/capabilities", headers=INSPECTOR).json()
        engines = {item["name"]: item for item in body["engines"]}
        assert "vector_text" in engines
        assert engines["vector_text"]["status"] == "AVAILABLE"
        assert engines["ocr_text"]["status"] == "UNAVAILABLE"
        assert engines["ocr_text"]["affects_verdict"] is True

    def test_health_is_list_dict_not_flat_map(self) -> None:
        # RT-2: health — {healthy: [...], degraded: [...], ...}
        body = self.client.get("/api/v1/system/capabilities", headers=INSPECTOR).json()
        health = body["health"]
        assert isinstance(health, dict)
        assert "healthy" in health
        assert "failed" in health
        assert "skipped" in health
        # Честно: OCR/чертёж в failed, не в healthy
        assert "ocr_text" in health["failed"]
        assert "vector_text" in health["healthy"]
        assert "llm_advisory" in health["skipped"]


# ---------------------------------------------------------------------------
# RT-4: pdf_guard актуальный API
# ---------------------------------------------------------------------------

class TestPdfGuardActualAPI:
    """RT-4: API - run_pdf_parse_sync / run_pdf_parse. Нет parse_with_timeout."""

    # Вспомогательные parser-функции (bytes -> T)
    @staticmethod
    def _ok(data: bytes) -> str:
        return data.decode("ascii")

    @staticmethod
    def _slow(data: bytes) -> str:
        time.sleep(0.4)
        return data.decode("ascii")

    @staticmethod
    def _raises(data: bytes) -> str:
        raise ValueError("corrupt pdf")

    def test_sync_success(self) -> None:
        # run_pdf_parse_sync(парсер, байты, *, timeout_s)
        assert run_pdf_parse_sync(self._ok, b"pdf", timeout_s=1.0) == "pdf"

    def test_sync_timeout_raises_typed_error(self) -> None:
        with pytest.raises(PdfParseTimeoutError, match="превысил"):
            run_pdf_parse_sync(self._slow, b"pdf", timeout_s=0.05)

    def test_zero_timeout_is_invalid_not_passthrough(self) -> None:
        # RT-4: timeout_s=0 — ValueError, не pass-through
        with pytest.raises(ValueError, match="положительным"):
            run_pdf_parse_sync(self._ok, b"x", timeout_s=0)

    def test_timeout_error_has_no_process_id_field(self) -> None:
        # RT-4: PdfParseTimeoutError не имеет process_id атрибута
        with pytest.raises(PdfParseTimeoutError) as exc_info:
            run_pdf_parse_sync(self._slow, b"pdf", timeout_s=0.05)
        assert not hasattr(exc_info.value, "process_id")

    def test_async_success(self) -> None:
        async def _run() -> str:
            return await run_pdf_parse(self._ok, b"ok", timeout_s=1.0)
        assert asyncio.run(_run()) == "ok"

    def test_async_timeout_raises_typed_error(self) -> None:
        async def _run() -> None:
            await run_pdf_parse(self._slow, b"pdf", timeout_s=0.05)
        with pytest.raises(PdfParseTimeoutError, match="превысил"):
            asyncio.run(_run())

    def test_exception_from_parser_propagates(self) -> None:
        with pytest.raises(ValueError, match="corrupt pdf"):
            run_pdf_parse_sync(self._raises, b"x", timeout_s=1.0)


# ---------------------------------------------------------------------------
# RT-6: Finding не издаёт UserWarning (нет в коде)
# ---------------------------------------------------------------------------

class TestFindingNoUserWarning:
    """RT-6: нет UserWarning в __post_init__ Finding на main."""

    def _make(self, **kwargs: object) -> Finding:
        defaults: dict[str, object] = dict(
            finding_id="f-rt6",
            rule_code="IOS4-078",
            finding_status=FindingStatus.MISSING_EVIDENCE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="1.0",
            rule_version="1.0",
            model_version="0.1",
        )
        defaults.update(kwargs)
        return Finding(**defaults)  # type: ignore[arg-type]

    def test_finding_with_group_id_and_no_source_id_does_not_warn(self) -> None:
        # RT-6: PR #36 ожидал UserWarning — его нет в коде
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self._make(
                finding_status=FindingStatus.CANDIDATE,
                evidence_group_id="eg-001",
                source_id=None,
            )
        user_warns = [x for x in w if issubclass(x.category, UserWarning)]
        assert len(user_warns) == 0, "Finding не емитирует UserWarning в main"

    def test_has_provenance_requires_both_evidence_group_id_and_source_id(self) -> None:
        # has_provenance = bool(evidence_group_id) AND bool(source_id)
        f_both = self._make(
            finding_status=FindingStatus.CANDIDATE,
            evidence_group_id="eg-1",
            source_id="pd:p1:frag-x",
        )
        f_only_group = self._make(
            finding_status=FindingStatus.CANDIDATE,
            evidence_group_id="eg-1",
            source_id=None,
        )
        f_only_source = self._make(source_id="pd:p1:frag-x")
        assert f_both.has_provenance is True
        assert f_only_group.has_provenance is False  # source_id отсутствует
        assert f_only_source.has_provenance is False  # evidence_group_id отсутствует

    def test_disagreement_kind_enum_values(self) -> None:
        assert {k.value for k in DisagreementKind} == {
            "VALUE_DELTA",
            "MISSING_IN_STAGE",
            "AMBIGUOUS_REFERENCE",
            "FORMAT_MISMATCH",
        }

    def test_finding_stores_disagreement_kind(self) -> None:
        f = self._make(disagreement_kind=DisagreementKind.VALUE_DELTA)
        assert f.disagreement_kind is DisagreementKind.VALUE_DELTA

    def test_finding_stores_source_id_and_refs(self) -> None:
        f = self._make(
            source_id="pd:p12:frag-abc",
            evidence_refs=("frag-1", "frag-2"),
        )
        assert f.source_id == "pd:p12:frag-abc"
        assert f.evidence_refs == ("frag-1", "frag-2")


# ---------------------------------------------------------------------------
# GAP-IOS4-VAL: зафиксировано поведение (прокси ширины, не площадь)
# ---------------------------------------------------------------------------

class TestIos4GapDocumented:
    """GAP-IOS4-VAL: экстрактор берёт первую сторону сечения, не площадь.
    Зафиксировано в KNOWN_GAPS.md как GAP-IOS4-VAL.
    Gate J (отзыв на frozen val) закрыть нельзя до исправления.
    """

    def test_gap_ios4_val_is_documented_in_known_gaps(
        self, tmp_path: pytest.TempPathFactory
    ) -> None:
        from pathlib import Path

        gaps_path = Path(__file__).resolve().parents[2] / "docs" / "KNOWN_GAPS.md"
        content = gaps_path.read_text(encoding="utf-8")
        # GAP-IOS4-VAL обязан быть в реестре
        assert "GAP-IOS4-VAL" in content
        # Gate J ссылка обязательна
        assert "гейт" in content.lower() or "gate" in content.lower()

    def test_gap_isolate_is_documented(self) -> None:
        from pathlib import Path

        gaps_path = Path(__file__).resolve().parents[2] / "docs" / "KNOWN_GAPS.md"
        content = gaps_path.read_text(encoding="utf-8")
        assert "GAP-ISOLATE" in content

    def test_split_raises_not_implemented(self) -> None:
        from kontur.application.review import split
        from kontur.domain.state_machines import TransitionError

        f = Finding(
            finding_id="f-split",
            rule_code="IOS4-078",
            finding_status=FindingStatus.MISSING_EVIDENCE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="1.0",
            rule_version="1.0",
            model_version="0.1",
        )
        with pytest.raises(NotImplementedError):
            split(f, parts=2)
