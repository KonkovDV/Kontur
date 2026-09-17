"""Сбой advisory-модели не валит комплект."""

from __future__ import annotations

from kontur.domain.capabilities import CapStatus, describe, kit_blocked


def test_llm_advisory_down_does_not_block_the_kit() -> None:
    caps = (
        describe("vector_text", CapStatus.AVAILABLE),
        describe("llm_advisory", CapStatus.UNAVAILABLE),
    )
    assert caps[1].affects_verdict is False
    assert kit_blocked(caps) is False


def test_missing_ocr_blocks_when_it_affects_verdict() -> None:
    caps = (describe("ocr_text", CapStatus.UNAVAILABLE),)
    assert caps[0].affects_verdict is True
    assert kit_blocked(caps) is True
