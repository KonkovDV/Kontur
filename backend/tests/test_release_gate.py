"""Гейт публикации модели: подпись, категории, пороги по Wilson."""

from __future__ import annotations

import pytest

from kontur.evaluation.metrics import TZ_THRESHOLDS, Interval, wilson
from kontur.evaluation.release_gate import (
    REQUIRED_CATEGORIES,
    PublicationSignature,
    evaluate,
)


def _passing_intervals() -> dict[str, Interval]:
    return {
        name: wilson(990, 1000) if name != "false_positive_rate" else wilson(10, 1000)
        for name in TZ_THRESHOLDS
    }


def _signature() -> PublicationSignature:
    return PublicationSignature(
        responsible_id="inspector-1",
        model_version="m-test",
        rollback_plan="revert to m-prev",
    )


def _recall() -> dict[str, float]:
    return {category: 0.90 for category in REQUIRED_CATEGORIES}


def test_missing_signature_blocks() -> None:
    result = evaluate(
        intervals=_passing_intervals(),
        recall_by_category=_recall(),
        baseline_recall_by_category=_recall(),
        fpr_by_group={"all": 0.02},
        baseline_fpr_by_group={"all": 0.02},
        signature=None,
    )
    assert result.passed is False
    assert any("PublicationSignature" in item for item in result.blocking)


def test_missing_category_blocks() -> None:
    recall = {category: 0.90 for category in REQUIRED_CATEGORIES if category != "KR"}
    result = evaluate(
        intervals=_passing_intervals(),
        recall_by_category=recall,
        baseline_recall_by_category=recall,
        fpr_by_group={"all": 0.02},
        baseline_fpr_by_group={"all": 0.02},
        signature=_signature(),
    )
    assert result.passed is False
    assert any("KR" in item for item in result.blocking)


@pytest.mark.parametrize("field", ["responsible_id", "model_version", "rollback_plan"])
def test_empty_signature_fields_are_rejected(field: str) -> None:
    kwargs = {
        "responsible_id": "inspector-1",
        "model_version": "m-test",
        "rollback_plan": "revert to m-prev",
    }
    kwargs[field] = "  "
    with pytest.raises(ValueError, match=field):
        PublicationSignature(**kwargs)


def test_required_categories_are_the_six_tz_sections() -> None:
    assert REQUIRED_CATEGORIES == frozenset({"PZ", "KR", "AR", "IOS", "SM", "OOS"})


def test_recall_drop_over_two_pp_blocks() -> None:
    current = _recall()
    current = {**current, "KR": 0.80}
    baseline = _recall()
    result = evaluate(
        intervals=_passing_intervals(),
        recall_by_category=current,
        baseline_recall_by_category=baseline,
        fpr_by_group={"all": 0.02},
        baseline_fpr_by_group={"all": 0.02},
        signature=_signature(),
    )
    assert result.passed is False
    assert any("recall[KR]" in item for item in result.blocking)


def test_fpr_rise_over_two_pp_blocks() -> None:
    result = evaluate(
        intervals=_passing_intervals(),
        recall_by_category=_recall(),
        baseline_recall_by_category=_recall(),
        fpr_by_group={"all": 0.05},
        baseline_fpr_by_group={"all": 0.02},
        signature=_signature(),
    )
    assert result.passed is False
    assert any("fpr[all]" in item for item in result.blocking)


def test_missing_interval_blocks() -> None:
    intervals = _passing_intervals()
    del intervals["evidence_localization"]
    result = evaluate(
        intervals=intervals,
        recall_by_category=_recall(),
        baseline_recall_by_category=_recall(),
        fpr_by_group={"all": 0.02},
        baseline_fpr_by_group={"all": 0.02},
        signature=_signature(),
    )
    assert result.passed is False
    assert any("evidence_localization" in item for item in result.blocking)


def test_signed_full_set_can_pass() -> None:
    result = evaluate(
        intervals=_passing_intervals(),
        recall_by_category=_recall(),
        baseline_recall_by_category=_recall(),
        fpr_by_group={"all": 0.02},
        baseline_fpr_by_group={"all": 0.02},
        signature=_signature(),
    )
    assert result.passed is True
    assert result.blocking == ()
