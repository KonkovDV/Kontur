"""Гейт публикации модели (ТЗ п. 9.4).

Модель допускается в контур только при прохождении всех обязательных порогов
раздела 14, без просадки Recall по любой обязательной категории более чем на
2 п.п. и без роста FPR на проверенных отрицательных группах более чем на 2 п.п.
Решение подписывается ответственным лицом; откат обязан оставаться возможным.
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.evaluation.metrics import TZ_THRESHOLDS, Interval, meets_threshold

MAX_RECALL_DROP_PP = 2.0
MAX_FPR_RISE_PP = 2.0


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    blocking: tuple[str, ...]


def evaluate(
    *,
    intervals: dict[str, Interval],
    recall_by_category: dict[str, float],
    baseline_recall_by_category: dict[str, float],
    fpr_by_group: dict[str, float],
    baseline_fpr_by_group: dict[str, float],
) -> GateResult:
    blocking: list[str] = []

    for name in TZ_THRESHOLDS:
        interval = intervals.get(name)
        if interval is None:
            blocking.append(f"{name}: не измерено")
            continue
        if not meets_threshold(name, interval):
            blocking.append(f"{name}: порог не подтверждён интервалом")

    for category, value in recall_by_category.items():
        baseline = baseline_recall_by_category.get(category)
        if baseline is not None and (baseline - value) * 100 > MAX_RECALL_DROP_PP:
            blocking.append(f"recall[{category}]: просадка больше {MAX_RECALL_DROP_PP} п.п.")

    for group, value in fpr_by_group.items():
        baseline = baseline_fpr_by_group.get(group)
        if baseline is not None and (value - baseline) * 100 > MAX_FPR_RISE_PP:
            blocking.append(f"fpr[{group}]: рост больше {MAX_FPR_RISE_PP} п.п.")

    return GateResult(passed=not blocking, blocking=tuple(blocking))
