"""Остановка каскада. Проверяется не работа кода, а невозможность выдумать статус."""

from __future__ import annotations

import pytest

from kontur.application.pipeline import (
    NON_HALTING_STAGES,
    STAGE_FAILURE_STATUS,
    Stage,
    StageHaltError,
    StageResult,
    halt_status,
    run,
)
from kontur.domain.statuses import FindingStatus


def test_every_automatic_stage_has_safe_halt_status() -> None:
    for stage in Stage:
        if stage is Stage.L0_INTAKE or stage in NON_HALTING_STAGES:
            continue
        assert stage in STAGE_FAILURE_STATUS, stage.name
        assert halt_status(stage) is not FindingStatus.CONFIRMED_VIOLATION


def test_l0_is_rejection_not_finding_halt() -> None:
    with pytest.raises(ValueError, match="RejectionReason"):
        halt_status(Stage.L0_INTAKE)


def test_halt_never_produces_violation() -> None:
    assert FindingStatus.CONFIRMED_VIOLATION not in set(STAGE_FAILURE_STATUS.values())
    assert Stage.L0_INTAKE not in STAGE_FAILURE_STATUS


def test_review_stages_do_not_get_automatic_status() -> None:
    for stage in sorted(NON_HALTING_STAGES):
        with pytest.raises(StageHaltError):
            halt_status(stage)


def test_failed_review_stage_requires_explicit_status() -> None:
    with pytest.raises(StageHaltError):
        run([StageResult(Stage.L8_REVIEW, ok=False)])


def test_explicit_status_on_review_stage_is_kept() -> None:
    result = run([StageResult(Stage.L9_PROTOCOL, ok=False, status=FindingStatus.ABSTAIN)])
    assert result is FindingStatus.ABSTAIN


def test_l0_explicit_finding_status_cannot_bypass_rejection() -> None:
    with pytest.raises(ValueError, match="RejectionReason"):
        run(
            [
                StageResult(
                    Stage.L0_INTAKE,
                    ok=False,
                    status=FindingStatus.CONFIRMED_VIOLATION,
                )
            ]
        )


def test_cascade_cannot_assign_human_only_status() -> None:
    with pytest.raises(StageHaltError, match="инспектор"):
        run(
            [
                StageResult(
                    Stage.L8_REVIEW,
                    ok=False,
                    status=FindingStatus.CONFIRMED_VIOLATION,
                )
            ]
        )


def test_earliest_failure_wins() -> None:
    stages = [
        StageResult(Stage.L0_INTAKE, ok=True),
        StageResult(Stage.L5_PAIRING, ok=False),
        StageResult(Stage.L2_EXTRACTION, ok=False),
    ]
    assert run(stages) is FindingStatus.LOW_QUALITY


def test_clean_cascade_reaches_comparison() -> None:
    stages = [StageResult(stage, ok=True) for stage in Stage if stage <= Stage.L7_FINDINGS]
    assert run(stages) is None
