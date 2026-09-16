"""Верификация инспектором: атомарность, обязательная причина, финализация."""

from __future__ import annotations

from dataclasses import replace

import pytest

from kontur.application.review import can_finalize, review
from kontur.domain.models import Finding
from kontur.domain.state_machines import Actor, TransitionError
from kontur.domain.statuses import FindingStatus, ReasonCode, ReviewPriority

INSPECTOR = Actor("inspector-1", is_human=True)


def candidate(finding_id: str = "f-1") -> Finding:
    return Finding(
        finding_id=finding_id,
        evidence_group_id="eg-1",
        rule_code="AR-41",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
    )


def test_confirm_records_decision_and_counts_as_violation() -> None:
    result = review(candidate(), actor=INSPECTOR, action="CONFIRM")
    assert result.finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert result.inspector_decision is not None
    assert result.counts_as_violation


def test_reject_without_reason_code_is_refused() -> None:
    with pytest.raises(TransitionError):
        review(candidate(), actor=INSPECTOR, action="REJECT")


def test_reject_with_reason_code() -> None:
    result = review(
        candidate(), actor=INSPECTOR, action="REJECT", reason_code=ReasonCode.OCR_ERROR
    )
    assert result.finding_status is FindingStatus.NEGATIVE_VERIFIED
    assert not result.counts_as_violation


def test_automation_cannot_review() -> None:
    with pytest.raises(TransitionError):
        review(candidate(), actor=Actor("worker", is_human=False), action="CONFIRM")


def test_finalize_blocked_by_open_candidate() -> None:
    ok, pending = can_finalize([candidate("f-1")])
    assert not ok
    assert pending == ["f-1"]


def test_missing_evidence_does_not_block_finalize() -> None:
    stalled = replace(candidate("f-2"), finding_status=FindingStatus.MISSING_EVIDENCE)
    ok, pending = can_finalize([stalled])
    assert ok
    assert pending == []
