"""Измерение recall по правилам (GAP-IOS4-VAL, Gate J ⇒ 25.09).

Считается по evidence_group, не по страницам или файлам. Порог recall = 0.80 по
нижней границе Wilson (ТЗ п. 14.3), не по точечной оценке.
Внутренная цель (INTERNAL_TARGETS) = 0.88.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from kontur.evaluation.metrics import Interval, TZ_THRESHOLDS, meets_threshold, wilson


@dataclass(frozen=True, slots=True)
class RecallReport:
    rule_code: str
    interval: Interval
    threshold: float
    passes: bool

    def summary(self) -> str:
        status = "✅ PASS" if self.passes else "❌ FAIL"
        return (
            f"{status} {self.rule_code}: "
            f"recall={self.interval.point:.3f} "
            f"[{self.interval.low:.3f}, {self.interval.high:.3f}] "
            f"(n={self.interval.n}, threshold>={self.threshold:.2f})"
        )


def compute_recall(
    predictions: list[str | None],
    gold: list[str],
    *,
    match_fn: Callable[[str, str | None], bool] | None = None,
) -> Interval:
    """Доля правильно найденных из золотого набора.

    :param predictions: результаты автомата; None = пропущено
    :param gold:        эталонные значения (есть нарушение)
    :param match_fn:    предикат (gold, pred) -> bool; по умолчанию — Exact Match
    :return:            Wilson-интервал
    """
    if len(predictions) != len(gold):
        raise ValueError(
            f"predictions и gold должны быть одинаковой длины: "
            f"{len(predictions)} != {len(gold)}"
        )
    n = len(gold)
    if n == 0:
        return wilson(0, 0)

    if match_fn is None:
        def match_fn(g: str, p: str | None) -> bool:  # type: ignore[misc]
            return p is not None and p.strip() == g.strip()

    successes = sum(1 for g, p in zip(gold, predictions) if match_fn(g, p))
    return wilson(successes, n)


def rule_recall_report(
    rule_code: str,
    pairs: list[tuple[str, str | None]],
    *,
    match_fn: Callable[[str, str | None], bool] | None = None,
) -> RecallReport:
    """Полный отчёт по правилу. pairs = [(gold, predicted), ...]."""
    gold_list = [g for g, _ in pairs]
    pred_list = [p for _, p in pairs]
    interval = compute_recall(pred_list, gold_list, match_fn=match_fn)
    threshold = TZ_THRESHOLDS["recall"]
    passes = meets_threshold("recall", interval)
    return RecallReport(
        rule_code=rule_code,
        interval=interval,
        threshold=threshold,
        passes=passes,
    )
