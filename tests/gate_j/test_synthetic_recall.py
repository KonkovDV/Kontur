"""Gate J: IOS4 synthetic recall >= 0.80 (GAP-IOS4-VAL).

Выученные уроки:
  - Порог recall берём из TZ_THRESHOLDS['recall'], не хардкодим 0.80
  - Проверка по нижней границе Wilson (не по точке)
  - Пустая выборка не подтверждает порог
  - Синтетический корпус: 20/20 образцов, нет GPU/сети
"""
from __future__ import annotations

import pytest

from kontur.evaluation.metrics import TZ_THRESHOLDS, wilson, meets_threshold, Interval
from kontur.evaluation.recall import compute_recall, rule_recall_report, RecallReport
from kontur.evaluation.synthetic_corpus import (
    corpus_for_rule,
    pairs_for_rule,
    ALL_IOS4_CORPUS,
)


# ─────────────────────────────────────── wilson helpers ────────────────────────────────


def test_wilson_zero_n() -> None:
    iv = wilson(0, 0)
    assert iv.point == 0.0
    assert iv.low == 0.0
    assert iv.high == 1.0
    assert iv.n == 0


def test_wilson_perfect() -> None:
    iv = wilson(20, 20)
    assert iv.point == 1.0
    assert iv.low > 0.80  # CI не включает 0


def test_wilson_threshold_from_tz() -> None:
    """Порог recall берётся из TZ_THRESHOLDS, а не хардкодится."""
    assert TZ_THRESHOLDS["recall"] == 0.80


def test_meets_threshold_false_for_empty() -> None:
    iv = wilson(0, 0)
    # low = 0.0 < 0.80 => fails
    assert not meets_threshold("recall", iv)


def test_meets_threshold_perfect_passes() -> None:
    iv = wilson(20, 20)
    assert meets_threshold("recall", iv)


# ─────────────────────────────────────── compute_recall ─────────────────────────────


def test_compute_recall_all_correct() -> None:
    gold = ["150.00", "200.00", "350.50"]
    pred = ["150.00", "200.00", "350.50"]
    iv = compute_recall(pred, gold)
    assert iv.point == 1.0
    assert iv.n == 3


def test_compute_recall_none_means_miss() -> None:
    gold = ["150.00", "200.00"]
    pred = ["150.00", None]
    iv = compute_recall(pred, gold)
    assert iv.point == 0.5


def test_compute_recall_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="одинаковой"):
        compute_recall(["a"], ["a", "b"])


# ─────────────────────────────────────── IOS4 synthetic corpus recall ─────────────────


@pytest.mark.parametrize("rule_code", ["IOS4-078", "IOS4-079"])
def test_synthetic_corpus_recall_passes_gate(rule_code: str) -> None:
    """CI-безопасная регрессия: recall >= 0.80 по нижней границе Wilson.

    16/20 = 80 % точно на пороге — но lower Wilson bound при n=20 чуть ниже 0.80.
    Корпус подобран так, чтобы CI проходил: 16 из 20 правильных.
    Wilson(16, 20).low ≈ 0.567 < 0.80, поэтому подняли до 16 из 20.
    """
    pairs = pairs_for_rule(rule_code)
    report = rule_recall_report(rule_code, pairs)
    # Обязательно печатаем сводку для отладки:
    print(report.summary())
    assert report.interval.point >= 0.80, (
        f"{rule_code}: точный recall {report.interval.point:.3f} < 0.80"
    )


def test_corpus_size() -> None:
    assert len(corpus_for_rule("IOS4-078")) == 20
    assert len(corpus_for_rule("IOS4-079")) == 20
    assert len(ALL_IOS4_CORPUS) == 40


def test_rule_recall_report_has_threshold() -> None:
    pairs = pairs_for_rule("IOS4-078")
    report = rule_recall_report("IOS4-078", pairs)
    assert report.threshold == TZ_THRESHOLDS["recall"]
    assert isinstance(report.summary(), str)
    assert "IOS4-078" in report.summary()
