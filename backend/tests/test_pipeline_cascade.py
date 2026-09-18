"""Gate F: каскад L0–L9 (ТЗ п. 9.2, шаг 3).

Проверяет:
- halt_status() для каждой стадии L1–L7
- StageHaltError при попытке остановки на L8–L9
- pipeline.run(): первый сбой прекращает каскад, возвращает безопасный статус
- pipeline.run(): все L1–L7 пройдены → None (разрешено предметное сравнение)
- pipeline.run(): пропущенные обязательные стадии → StageHaltError
- pipeline.run(): сбой на L0 → ValueError (не finding)
"""

from __future__ import annotations

import pytest

from kontur.application.pipeline import (
    Stage,
    StageHaltError,
    StageResult,
    halt_status,
    run,
)
from kontur.domain.statuses import FindingStatus


class TestHaltStatus:
    @pytest.mark.parametrize(
        "stage,expected",
        [
            (Stage.L1_IDENTITY, FindingStatus.CLARIFICATION_REQUIRED),
            (Stage.L2_EXTRACTION, FindingStatus.LOW_QUALITY),
            (Stage.L3_LOCALIZATION, FindingStatus.LOW_QUALITY),
            (Stage.L4_REVISION, FindingStatus.CLARIFICATION_REQUIRED),
            (Stage.L5_PAIRING, FindingStatus.NOT_COMPARABLE),
            (Stage.L6_MATRIX, FindingStatus.CLARIFICATION_REQUIRED),
            (Stage.L7_FINDINGS, FindingStatus.ABSTAIN),
        ],
    )
    def test_halt_status_per_stage(self, stage: Stage, expected: FindingStatus) -> None:
        assert halt_status(stage) is expected

    def test_l0_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="L0"):
            halt_status(Stage.L0_INTAKE)

    def test_l8_raises_stage_halt_error(self) -> None:
        with pytest.raises(StageHaltError):
            halt_status(Stage.L8_REVIEW)

    def test_l9_raises_stage_halt_error(self) -> None:
        with pytest.raises(StageHaltError):
            halt_status(Stage.L9_PROTOCOL)


def _ok(stage: Stage) -> StageResult:
    return StageResult(stage=stage, ok=True)


def _fail(stage: Stage, status: FindingStatus | None = None) -> StageResult:
    return StageResult(stage=stage, ok=False, status=status)


def _all_ok() -> list[StageResult]:
    return [_ok(s) for s in [
        Stage.L1_IDENTITY, Stage.L2_EXTRACTION, Stage.L3_LOCALIZATION,
        Stage.L4_REVISION, Stage.L5_PAIRING, Stage.L6_MATRIX, Stage.L7_FINDINGS,
    ]]


class TestRun:
    def test_all_pass_returns_none(self) -> None:
        assert run(_all_ok()) is None

    def test_first_failure_stops_cascade(self) -> None:
        """Сбой L2 → LOW_QUALITY; L3–L7 не выполняются (не влияют)."""
        stages = _all_ok()
        stages[1] = _fail(Stage.L2_EXTRACTION)  # L2 fails
        result = run(stages)
        assert result is FindingStatus.LOW_QUALITY

    def test_l1_failure(self) -> None:
        stages = _all_ok()
        stages[0] = _fail(Stage.L1_IDENTITY)
        assert run(stages) is FindingStatus.CLARIFICATION_REQUIRED

    def test_l5_failure(self) -> None:
        stages = _all_ok()
        stages[4] = _fail(Stage.L5_PAIRING)
        assert run(stages) is FindingStatus.NOT_COMPARABLE

    def test_l7_failure(self) -> None:
        stages = _all_ok()
        stages[6] = _fail(Stage.L7_FINDINGS)
        assert run(stages) is FindingStatus.ABSTAIN

    def test_explicit_status_overrides_default(self) -> None:
        """Явный status на StageResult перебивает STAGE_FAILURE_STATUS."""
        stages = _all_ok()
        stages[1] = _fail(Stage.L2_EXTRACTION, status=FindingStatus.CLARIFICATION_REQUIRED)
        assert run(stages) is FindingStatus.CLARIFICATION_REQUIRED

    def test_missing_stage_raises_stage_halt_error(self) -> None:
        """Пропуск обязательной стадии — StageHaltError, не молчаливый допуск."""
        stages = _all_ok()
        stages.pop()  # убираем L7
        with pytest.raises(StageHaltError, match="L7"):
            run(stages)

    def test_empty_stages_raises_stage_halt_error(self) -> None:
        with pytest.raises(StageHaltError):
            run([])

    def test_l0_failure_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="L0"):
            run([_fail(Stage.L0_INTAKE)] + _all_ok())

    def test_order_independent_first_failure_wins(self) -> None:
        """run() сортирует по стадии; порядок передачи не важен."""
        stages = list(reversed(_all_ok()))
        stages[0] = _fail(Stage.L7_FINDINGS)  # L7 в начале списка
        stages[6] = _fail(Stage.L1_IDENTITY)  # L1 в конце списка
        # L1 < L7 → первый отказ = L1 = CLARIFICATION_REQUIRED
        assert run(stages) is FindingStatus.CLARIFICATION_REQUIRED
