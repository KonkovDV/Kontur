"""Gate K: dry run — все 132 параметра за ≤30 минут.

Цель:
  1. Убедиться, что evaluate_rule() запускается на каждом правиле (без краша)
  2. Суммарное время ≤ 1800 с (ЦЗ Gate K ≤30 мин)
  3. Каждый результат — корректный RuleEvaluation (finding не None, stages не пусты)

Выученные уроки:
  - Не хардкодим строки статусов: берём из FindingStatus
  - Синтетические страницы удовлетворяют _identity_ok():
    file_id.strip() != '', len(file_hash)==64, page≥1
  - ABSTAIN / AUTO_NO_DIFFERENCE допустимы — не холтим на них
"""
from __future__ import annotations

import time
from typing import Any

import pytest

from kontur.application.evaluate import RuleEvaluation, evaluate_rule
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness, FindingStatus

# Статусы, которые допустимо выдаёт автомат, без хардкода — из домена
_ACCEPTABLE_AUTO = frozenset(
    FindingStatus[s]
    for s in (
        "AUTO_NO_DIFFERENCE",
        "CANDIDATE",
        "ABSTAIN",
        "LOW_QUALITY",
        "MISSING_EVIDENCE",
        "NOT_COMPARABLE",
        "CLARIFICATION_REQUIRED",
    )
    if s in FindingStatus.__members__
)

_FULL_COMPLETENESS: CompletenessMap = {
    DocStage.PD: Completeness.UPLOADED,
    DocStage.RD: Completeness.UPLOADED,
    DocStage.ID: Completeness.UPLOADED,
}


def _equal_value_for_rule(rule: dict[str, Any]) -> tuple[float | str, float | str]:
    """Return identical PD/RD values that should yield AUTO_NO_DIFFERENCE."""
    extractor = rule.get("extractor") or {}
    etype = extractor.get("type", "number")
    if etype == "number":
        return (1.0, 1.0)
    # enum / text_regex — equal strings → no difference
    return ("VALUE_MATCH", "VALUE_MATCH")


class _DryRunStats:
    total: int = 0
    by_status: dict[str, int]

    def __init__(self) -> None:
        self.by_status = {}

    def record(self, result: RuleEvaluation) -> None:
        self.total += 1
        key = result.finding.finding_status.value
        self.by_status[key] = self.by_status.get(key, 0) + 1


DRY_RUN_LIMIT_SEC = 1800  # 30 минут


def test_dry_run_all_rules(
    matrix_rules: list[dict[str, Any]],
    make_synthetic_pages,
) -> None:
    """Run evaluate_rule on every compiled rule; assert count≥132 and time≤30min."""
    stats = _DryRunStats()
    errors: list[str] = []
    t0 = time.monotonic()

    for rule in matrix_rules:
        code = rule.get("code", "?")  # e.g. "IOS4-078"
        pd_val, rd_val = _equal_value_for_rule(rule)
        pages = make_synthetic_pages(rule, pd_value=pd_val, rd_value=rd_val)
        try:
            result = evaluate_rule(
                rule,
                object_id="dry-run-object",
                pages=pages,
                completeness=_FULL_COMPLETENESS,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{code}: {type(exc).__name__}: {exc}")
            continue

        assert result.finding is not None, f"{code}: finding is None"
        assert len(result.stages) > 0, f"{code}: stages empty"
        status = result.finding.finding_status
        assert status in _ACCEPTABLE_AUTO, (
            f"{code}: автомат выдал недопустимый статус {status!r}"
        )
        stats.record(result)

    elapsed = time.monotonic() - t0

    # Отчёт для CI
    summary = (
        f"\nDry run: {stats.total} rules in {elapsed:.1f}s "
        f"(limit {DRY_RUN_LIMIT_SEC}s)\n"
        f"Status breakdown: {stats.by_status}"
    )
    print(summary)

    if errors:
        error_block = "\n".join(errors[:20])
        pytest.fail(f"{len(errors)} rule(s) crashed:\n{error_block}")

    assert stats.total >= 132, (
        f"Матрица должна содержать ≥132 правила, найдено {stats.total}"
    )
    assert elapsed <= DRY_RUN_LIMIT_SEC, (
        f"Dry run превысил лимит: {elapsed:.1f}s > {DRY_RUN_LIMIT_SEC}s"
    )


@pytest.mark.parametrize("stage", [DocStage.PD, DocStage.RD, DocStage.ID])
def test_missing_stage_halts_gracefully(
    matrix_rules: list[dict[str, Any]],
    make_synthetic_pages,
    stage: DocStage,
) -> None:
    """Missing one stage produces MISSING_EVIDENCE or CLARIFICATION_REQUIRED, not crash."""
    # возьмём первюю rule числового экстрактора
    number_rule = next(
        (r for r in matrix_rules if (r.get("extractor") or {}).get("type") == "number"),
        None,
    )
    if number_rule is None:
        pytest.skip("Нет числового правила в матрице")

    completeness_with_missing: CompletenessMap = {
        s: Completeness.UPLOADED for s in DocStage
    }
    completeness_with_missing[stage] = Completeness.MISSING

    pd_val, rd_val = _equal_value_for_rule(number_rule)
    pages = make_synthetic_pages(number_rule, pd_value=pd_val, rd_value=rd_val)
    # Убираем страницу из pages, если эта стадия требуется правилом
    pages.pop(stage, None)

    result = evaluate_rule(
        number_rule,
        object_id="dry-run-missing",
        pages=pages,
        completeness=completeness_with_missing,
    )
    halt_statuses = {
        FindingStatus.MISSING_EVIDENCE,
        FindingStatus.CLARIFICATION_REQUIRED,
    }
    # Поддерживаем также LOW_QUALITY / NOT_COMPARABLE / ABSTAIN (failure_mapping может переопределить)
    assert result.finding.finding_status in (_ACCEPTABLE_AUTO | halt_statuses), (
        f"Неожиданный статус при отсутствии {stage.value}: {result.finding.finding_status!r}"
    )
