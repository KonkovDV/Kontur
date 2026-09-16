"""Каскад L0–L9: отказ стадии — статус качества данных, не нарушение."""

from __future__ import annotations

import pytest

from kontur.application.pipeline import Stage, StageResult, halt_status, run
from kontur.domain.statuses import FindingStatus


def test_l0_failure_is_rejection_not_finding() -> None:
    with pytest.raises(ValueError, match="RejectionReason"):
        halt_status(Stage.L0_INTAKE)


def test_matrix_engine_failure_is_clarification() -> None:
    assert halt_status(Stage.L6_MATRIX) is FindingStatus.CLARIFICATION_REQUIRED


def test_pairing_failure_is_not_comparable() -> None:
    assert halt_status(Stage.L5_PAIRING) is FindingStatus.NOT_COMPARABLE


def test_first_failure_halts_cascade() -> None:
    status = run(
        [
            StageResult(Stage.L1_IDENTITY, ok=True),
            StageResult(Stage.L2_EXTRACTION, ok=False),
            StageResult(Stage.L6_MATRIX, ok=True),
        ]
    )
    assert status is FindingStatus.LOW_QUALITY


def test_all_stages_ok_admits_comparison() -> None:
    status = run([StageResult(stage, ok=True) for stage in Stage])
    assert status is None
