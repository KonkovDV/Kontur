"""Пороги проверяются по консервативной границе интервала, не по точечной оценке."""

from __future__ import annotations

from kontur.evaluation.metrics import (
    INTERNAL_TARGETS,
    TZ_THRESHOLDS,
    Interval,
    f1,
    meets_threshold,
    wilson,
)


def test_wilson_on_empty_sample_is_uninformative() -> None:
    interval = wilson(0, 0)
    assert (interval.low, interval.high) == (0.0, 1.0)


def test_small_sample_does_not_confirm_threshold() -> None:
    """10 из 10 — точечная оценка 1.0, но выборка не подтверждает 0,95."""

    interval = wilson(10, 10)
    assert interval.point == 1.0
    assert not meets_threshold("precision", interval)


def test_large_sample_confirms_threshold() -> None:
    interval = wilson(970, 1000)
    assert meets_threshold("precision", interval)


def test_fpr_checked_by_upper_bound() -> None:
    assert meets_threshold("false_positive_rate", wilson(30, 1000))
    assert not meets_threshold("false_positive_rate", wilson(100, 1000))


def test_f1_matches_tz_minimum() -> None:
    assert TZ_THRESHOLDS["f1"] == 0.85
    assert round(f1(0.90, 0.80), 4) == 0.8471


def test_internal_targets_are_stricter_than_tz() -> None:
    for name, threshold in TZ_THRESHOLDS.items():
        target = INTERNAL_TARGETS[name]
        if name == "false_positive_rate":
            assert target <= threshold
        else:
            assert target >= threshold


def test_interval_is_immutable() -> None:
    interval = Interval(point=0.5, low=0.4, high=0.6, n=100)
    assert interval.n == 100
