"""Сигналы SUSPICION: четыре подхода п. 9.5, дедупликация, запрет эскалации."""

from __future__ import annotations

import pytest

from kontur.application.suspicion import (
    SuspicionApproach,
    SuspicionSignal,
    assess_annotation_conflict,
    assess_dual_read_disagree,
    assess_low_confidence,
    assess_partial_match,
    deduplicate_by_group,
)
from kontur.domain.models import Finding
from kontur.domain.statuses import (
    HUMAN_ONLY_STATUSES,
    STATUSES_REQUIRING_EVIDENCE,
    VIOLATION_STATUSES,
    WIRE_FINDING_STATUSES,
    FindingStatus,
    ReviewPriority,
)


def test_low_confidence_below_threshold_generates_suspicion() -> None:
    signal = assess_low_confidence("PZ-001", "eg-001", confidence=0.45)
    assert signal is not None
    assert signal.approach is SuspicionApproach.LOW_CONFIDENCE
    assert signal.status is FindingStatus.SUSPICION
    assert signal.confidence == pytest.approx(0.45)
    assert signal.evidence_group_id == "eg-001"


def test_low_confidence_at_or_above_threshold_returns_none() -> None:
    assert assess_low_confidence("PZ-001", "eg-001", confidence=0.60) is None
    assert assess_low_confidence("PZ-001", "eg-001", confidence=0.99) is None


def test_low_confidence_custom_threshold() -> None:
    assert (
        assess_low_confidence("AR-041", "eg-002", confidence=0.75, low_confidence_threshold=0.80)
        is not None
    )
    assert (
        assess_low_confidence("AR-041", "eg-002", confidence=0.85, low_confidence_threshold=0.80)
        is None
    )


def test_dual_read_different_values_generates_suspicion() -> None:
    signal = assess_dual_read_disagree("KR-055", "eg-003", first_value=6, second_value=8)
    assert signal is not None
    assert signal.approach is SuspicionApproach.DUAL_READ_DISAGREE
    assert "6" in signal.detail and "8" in signal.detail
    assert signal.status is FindingStatus.SUSPICION


def test_dual_read_same_values_returns_none() -> None:
    assert assess_dual_read_disagree("KR-055", "eg-003", first_value=42, second_value=42) is None
    assert (
        assess_dual_read_disagree("KR-055", "eg-003", first_value="abc", second_value="abc") is None
    )


def test_partial_match_middle_ratio_generates_suspicion() -> None:
    signal = assess_partial_match("IOS4-079", "eg-004", matched_criteria=3, total_criteria=5)
    assert signal is not None
    assert signal.approach is SuspicionApproach.PARTIAL_MATCH
    assert "3/5" in signal.detail
    assert signal.confidence == pytest.approx(0.6)


def test_partial_match_extremes_return_none() -> None:
    assert assess_partial_match("IOS4-079", "eg-004", matched_criteria=0, total_criteria=5) is None
    assert assess_partial_match("IOS4-079", "eg-004", matched_criteria=5, total_criteria=5) is None
    assert assess_partial_match("IOS4-079", "eg-004", matched_criteria=0, total_criteria=0) is None


def test_annotation_conflict_with_description_generates_suspicion() -> None:
    signal = assess_annotation_conflict(
        "IOS4-078",
        "eg-005",
        conflict_description="версия A: 150 мм, версия B: 200 мм",
    )
    assert signal is not None
    assert signal.approach is SuspicionApproach.ANNOTATION_CONFLICT
    assert "150" in signal.detail


def test_annotation_conflict_empty_description_returns_none() -> None:
    assert assess_annotation_conflict("IOS4-078", "eg-005", conflict_description="  ") is None
    assert assess_annotation_conflict("IOS4-078", "eg-005", conflict_description="") is None


def test_deduplicate_keeps_highest_confidence() -> None:
    first = SuspicionSignal("PZ-001", "eg-100", SuspicionApproach.LOW_CONFIDENCE, 0.45, "low")
    second = SuspicionSignal("PZ-001", "eg-100", SuspicionApproach.DUAL_READ_DISAGREE, 0.55, "dual")
    result = deduplicate_by_group([first, second])
    assert len(result) == 1
    assert result[0].confidence == pytest.approx(0.55)
    assert result[0].approach is SuspicionApproach.DUAL_READ_DISAGREE


def test_deduplicate_different_groups_are_independent() -> None:
    first = SuspicionSignal("PZ-001", "eg-001", SuspicionApproach.LOW_CONFIDENCE, 0.45, "d1")
    second = SuspicionSignal("PZ-001", "eg-002", SuspicionApproach.LOW_CONFIDENCE, 0.50, "d2")
    assert len(deduplicate_by_group([first, second])) == 2


def test_deduplicate_different_rules_same_group_are_independent() -> None:
    first = SuspicionSignal("PZ-001", "eg-001", SuspicionApproach.LOW_CONFIDENCE, 0.40, "d1")
    second = SuspicionSignal("AR-041", "eg-001", SuspicionApproach.LOW_CONFIDENCE, 0.45, "d2")
    assert len(deduplicate_by_group([first, second])) == 2


def test_deduplicate_empty_input_returns_empty() -> None:
    assert deduplicate_by_group([]) == ()


def test_suspicion_without_evidence_group_id_raises() -> None:
    with pytest.raises(ValueError, match="evidence_group_id"):
        SuspicionSignal("PZ-001", "", SuspicionApproach.LOW_CONFIDENCE, 0.5, "detail")


def test_suspicion_confidence_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="confidence"):
        SuspicionSignal("PZ-001", "eg-001", SuspicionApproach.LOW_CONFIDENCE, 1.1, "detail")


def test_suspicion_cannot_be_confirmed_violation() -> None:
    with pytest.raises(ValueError, match="SUSPICION"):
        SuspicionSignal(
            "PZ-001",
            "eg-001",
            SuspicionApproach.LOW_CONFIDENCE,
            0.5,
            "detail",
            status=FindingStatus.CONFIRMED_VIOLATION,
        )


def test_suspicion_is_wire_serializable_and_not_a_violation() -> None:
    assert FindingStatus.SUSPICION in WIRE_FINDING_STATUSES
    assert FindingStatus.SUSPICION not in VIOLATION_STATUSES
    assert FindingStatus.SUSPICION not in HUMAN_ONLY_STATUSES
    assert FindingStatus.SUSPICION in STATUSES_REQUIRING_EVIDENCE


def test_finding_suspicion_requires_evidence_group() -> None:
    with pytest.raises(ValueError, match="evidence_group_id"):
        Finding(
            finding_id="f-s",
            rule_code="PZ-001",
            finding_status=FindingStatus.SUSPICION,
            review_priority=ReviewPriority.MEDIUM,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        )
