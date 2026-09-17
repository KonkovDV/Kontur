"""Пороги проверяются по консервативной границе интервала, не по точечной оценке."""

from __future__ import annotations

import pytest

from kontur.evaluation.metrics import (
    INTERNAL_TARGETS,
    TZ_THRESHOLDS,
    Interval,
    character_accuracy,
    f1,
    key_field_exact_match,
    key_field_exact_match_interval,
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


def test_f1_floor_is_stricter_than_precision_and_recall_floors() -> None:
    """P=0.90 и R=0.80 одновременно не закрывают порог F1=0.85."""

    assert TZ_THRESHOLDS["f1"] == 0.85
    harmonic = f1(TZ_THRESHOLDS["precision"], TZ_THRESHOLDS["recall"])
    assert round(harmonic, 4) == 0.8471
    assert harmonic < TZ_THRESHOLDS["f1"]


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


def test_key_field_exact_match_is_case_sensitive_in_ciphers() -> None:
    assert key_field_exact_match("12345-PZ", "12345-PZ")
    assert not key_field_exact_match("12345-PZ", "12345-pz")


def test_key_field_exact_match_uses_nfc_and_collapses_spaces() -> None:
    assert key_field_exact_match("12345-PZ", "  12345-PZ  ")
    assert key_field_exact_match("café-1", "cafe\u0301-1")
    assert not key_field_exact_match("12345-PZ", None)
    assert not key_field_exact_match("12345-PZ", "   ")


def test_key_field_threshold_needs_wilson_lower_bound() -> None:
    """Точечная 1.0 на 10 полях не закрывает порог ТЗ 0.90."""

    pairs = [("12345-PZ", "12345-PZ")] * 10
    interval = key_field_exact_match_interval(pairs)
    assert interval.point == 1.0
    assert not meets_threshold("key_field_exact_match", interval)
    empty = key_field_exact_match_interval([])
    assert empty.n == 0
    assert not meets_threshold("key_field_exact_match", empty)


def test_character_accuracy_is_not_exact_match() -> None:
    with pytest.raises(NotImplementedError, match="E1"):
        character_accuracy("12345-PZ", "12345-PZ")
