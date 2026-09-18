"""Tests: capability honesty endpoint (donor: AeroBIM).

Gate L: GET /api/v1/system/capabilities must:
  - Return 200 with overall_kit_status
  - Show 'failed' for any UNAVAILABLE verdict-affecting engine
  - Show 'skipped' (not 'failed') for advisory (LLM) engines
  - Propagate DEGRADED to overall_kit_status
  - Never let LLM status affect overall_kit_status
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kontur.domain.capabilities import CapStatus
from kontur.domain.engine_status import (
    EngineStatusKind,
    build_engine_report,
    kit_degraded_by_engine,
    serialise_report,
)
from kontur.presentation.api import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestGetSystemCapabilitiesEndpoint:
    """GET /api/v1/system/capabilities."""

    def test_returns_200_with_expected_keys(self, client: TestClient) -> None:
        resp = client.get("/api/v1/system/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_kit_status" in data
        assert "engines" in data
        assert isinstance(data["engines"], list)

    def test_default_statuses_give_ok(self, client: TestClient) -> None:
        # Default capability_statuses in skeleton: vector+ocr AVAILABLE, llm UNAVAILABLE
        resp = client.get("/api/v1/system/capabilities")
        data = resp.json()
        # vector_text + ocr_text + ocr_tables + drawing_analysis = AVAILABLE -> ok
        ok_engines = [e for e in data["engines"] if e["name"] == "vector_text"]
        assert ok_engines[0]["status"] == "ok"

    def test_llm_advisory_unavailable_shows_skipped_not_failed(
        self, client: TestClient
    ) -> None:
        # LLM is UNAVAILABLE by default but advisory_only → must be 'skipped'
        resp = client.get("/api/v1/system/capabilities")
        data = resp.json()
        llm_engines = [e for e in data["engines"] if e["name"] == "llm_advisory"]
        assert llm_engines, "llm_advisory should appear in the capability list"
        assert llm_engines[0]["status"] == "skipped"
        assert llm_engines[0]["affects_verdict"] is False


class TestEngineStatusDomain:
    """Unit tests for engine_status domain module."""

    def test_all_available_gives_ok_overall(self) -> None:
        statuses = {
            "vector_text": CapStatus.AVAILABLE,
            "ocr_text": CapStatus.AVAILABLE,
            "ocr_tables": CapStatus.AVAILABLE,
            "drawing_analysis": CapStatus.AVAILABLE,
            "llm_advisory": CapStatus.AVAILABLE,
        }
        reports = build_engine_report(statuses)
        assert not kit_degraded_by_engine(reports)
        serialised = serialise_report(reports)
        assert serialised["overall_kit_status"] == "OK"

    def test_verdict_engine_failed_propagates_degraded(self) -> None:
        statuses = {
            "vector_text": CapStatus.AVAILABLE,
            "ocr_text": CapStatus.UNAVAILABLE,  # verdict engine → FAILED → DEGRADED
            "ocr_tables": CapStatus.AVAILABLE,
            "drawing_analysis": CapStatus.AVAILABLE,
            "llm_advisory": CapStatus.AVAILABLE,
        }
        reports = build_engine_report(statuses)
        assert kit_degraded_by_engine(reports)
        serialised = serialise_report(reports)
        assert serialised["overall_kit_status"] == "DEGRADED"
        # Verify ocr_text shows as 'failed'
        ocr = next(e for e in serialised["engines"] if e["name"] == "ocr_text")
        assert ocr["status"] == EngineStatusKind.FAILED

    def test_llm_failed_does_not_degrade_kit(self) -> None:
        statuses = {
            "vector_text": CapStatus.AVAILABLE,
            "ocr_text": CapStatus.AVAILABLE,
            "ocr_tables": CapStatus.AVAILABLE,
            "drawing_analysis": CapStatus.AVAILABLE,
            "llm_advisory": CapStatus.DEGRADED,  # advisory → never raises DEGRADED
        }
        reports = build_engine_report(statuses)
        # LLM degraded → FAILED for that engine, but affects_verdict=False
        assert not kit_degraded_by_engine(reports)
        serialised = serialise_report(reports)
        assert serialised["overall_kit_status"] == "OK"
