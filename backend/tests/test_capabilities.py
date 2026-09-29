"""Сбой advisory-модели не валит комплект. Тишина не считается успехом."""

from __future__ import annotations

from kontur.domain.capabilities import (
    CapStatus,
    capabilities_payload,
    describe,
    engine_health_summary,
    kit_blocked,
    kit_degraded,
    live_kit,
    overall_kit_status,
)


def test_llm_advisory_down_does_not_block_the_kit() -> None:
    caps = (
        describe("vector_text", CapStatus.AVAILABLE),
        describe("llm_advisory", CapStatus.UNAVAILABLE),
    )
    assert caps[1].affects_verdict is False
    assert kit_blocked(caps) is False
    assert overall_kit_status(caps) is CapStatus.AVAILABLE


def test_missing_ocr_blocks_when_it_affects_verdict() -> None:
    caps = (describe("ocr_text", CapStatus.UNAVAILABLE),)
    assert caps[0].affects_verdict is True
    assert kit_blocked(caps) is True
    assert overall_kit_status(caps) is CapStatus.UNAVAILABLE


def test_degraded_verdict_layer_does_not_block() -> None:
    caps = (
        describe("vector_text", CapStatus.AVAILABLE),
        describe("ocr_text", CapStatus.DEGRADED),
    )
    assert kit_blocked(caps) is False
    assert kit_degraded(caps) is True
    assert overall_kit_status(caps) is CapStatus.DEGRADED


def test_health_summary_does_not_invent_healthy_engines() -> None:
    caps = (describe("vector_text", CapStatus.AVAILABLE),)
    health = engine_health_summary(caps)
    assert health["healthy"] == ["vector_text"]
    assert "ocr_text" in health["skipped"]
    assert "llm_advisory" in health["skipped"]
    assert "drawing_analysis" in health["skipped"]


def test_health_summary_failed_is_unavailable_verdict_layer() -> None:
    caps = (
        describe("vector_text", CapStatus.AVAILABLE),
        describe("ocr_text", CapStatus.UNAVAILABLE),
        describe("llm_advisory", CapStatus.UNAVAILABLE),
    )
    health = engine_health_summary(caps)
    assert "ocr_text" in health["failed"]
    assert "llm_advisory" in health["skipped"]


def test_payload_overall_follows_live_kit_not_missing_ocr() -> None:
    payload = capabilities_payload()
    assert payload["overall"] == "AVAILABLE"
    assert payload["kit_blocked"] is False
    assert live_kit()[0].name == "vector_text"
    engines = {item["name"]: item for item in payload["engines"]}  # type: ignore[misc]
    assert engines["vector_text"]["status"] == "AVAILABLE"
    assert engines["ocr_text"]["status"] == "MEASURED"
    assert engines["drawing_analysis"]["status"] == "DEGRADED"
    assert engines["ocr_text"]["affects_verdict"] is True
    health = payload["health"]
    assert isinstance(health, dict)
    assert "ocr_text" in health["measured"]
    assert "ocr_text" not in health["failed"]
    assert "ocr_text" not in health["healthy"]
    assert "vector_text" in health["healthy"]
    assert "overall_kit_status" not in payload
    assert "engine_status" not in payload
    assert "BLOCKED" not in {member.value for member in CapStatus}


def test_advisory_degraded_does_not_degrade_the_kit() -> None:
    caps = (describe("llm_advisory", CapStatus.DEGRADED),)
    assert kit_degraded(caps) is False
    assert overall_kit_status(caps) is CapStatus.AVAILABLE
