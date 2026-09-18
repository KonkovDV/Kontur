"""Замер recall на frozen val. Без корпуса цифры не публикуются.

Синтетический gold=pred и `tests/gate_j` вне pytest сюда не входят.
Порог ТЗ считается по нижней границе Wilson, не по точечной оценке.
Карантин скрытого теста (`test_213`, TEST_HIDDEN) читать нельзя.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from kontur.evaluation.inventory import require_path_open
from kontur.evaluation.metrics import Interval, meets_threshold, wilson

FROZEN_VAL_ENV = "KONTUR_FROZEN_VAL_PATH"


def resolve_corpus_path(env: Mapping[str, str] | None = None) -> Path | None:
    """Путь корпуса или None, если замер не запрошен. Карантин — исключение."""

    raw = (env or os.environ).get(FROZEN_VAL_ENV)
    if not raw or not raw.strip():
        return None
    return require_path_open(Path(raw))


def critical_recall(gold_positive: Sequence[bool], predicted: Sequence[bool]) -> Interval:
    """Recall по критическим позитивам. Длины обязаны совпадать."""

    if len(gold_positive) != len(predicted):
        raise ValueError("gold и pred разной длины")
    n = sum(1 for item in gold_positive if item)
    hits = sum(
        1
        for gold, pred in zip(gold_positive, predicted, strict=True)
        if gold and pred
    )
    return wilson(hits, n)


def recall_meets_tz(interval: Interval) -> bool:
    """True только если нижняя граница Wilson ≥ порога ТЗ."""

    return meets_threshold("recall", interval)
