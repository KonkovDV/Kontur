"""Замер на frozen val — opt-in. Без пути корпус не трогаем и цифры не публикуем."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kontur.evaluation.frozen_val import (
    FROZEN_VAL_ENV,
    critical_recall,
    recall_meets_tz,
    resolve_corpus_path,
)
from kontur.evaluation.inventory import QuarantineViolation
from kontur.evaluation.metrics import wilson


def test_frozen_val_is_skipped_without_corpus_path() -> None:
    path = os.environ.get(FROZEN_VAL_ENV)
    if not path:
        pytest.skip(f"{FROZEN_VAL_ENV} не задан; recall/P/F1 на frozen val не измеряются")
    corpus = Path(path)
    if not corpus.exists():
        pytest.skip(f"{FROZEN_VAL_ENV} указывает на отсутствующий путь: {corpus}")
    pytest.skip("замер метрик на frozen val не в этом прогоне: порог приёмки не публикуется")


def test_resolve_corpus_path_is_none_without_env() -> None:
    assert resolve_corpus_path({}) is None


def test_resolve_corpus_path_refuses_quarantine() -> None:
    with pytest.raises(QuarantineViolation):
        resolve_corpus_path({FROZEN_VAL_ENV: "data/quarantine/test_hidden"})


def test_synthetic_16_of_20_does_not_meet_tz_recall() -> None:
    """Точечная оценка 0.80 не закрывает порог: Wilson low < 0.80."""

    gold = [True] * 20
    pred = [True] * 16 + [False] * 4
    interval = critical_recall(gold, pred)
    assert interval.n == 20
    assert interval.point == 0.8
    assert not recall_meets_tz(interval)
    assert wilson(16, 20).low < 0.80
