"""Верификация инспектором: атомарность, обязательная причина, финализация."""

from __future__ import annotations

from dataclasses import replace

import pytest

from kontur.application.review import (
    can_finalize,
    complete_verification,
    finalize_process,
    review,
    select_revision_as_etalon,
    split,
    start_verification,
    unfinalize_process,
)
from kontur.domain.models import ApprovalStatus, Finding
from kontur.domain.state_machines import Actor, TransitionError
from kontur.domain.statuses import FindingStatus, ProcessState, ReasonCode, ReviewPriority

INSPECTOR = Actor("inspector-1", is_human=True)
SUPERVISOR = Actor("admin", is_human=True, is_supervisor=True)
COMMENT = "Расхождение подтверждено по листам ПД и РД."


class MemoryAudit:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def record(self, actor_id: str, action: str, payload: dict[str, object]) -> None:
        self.records.append((actor_id, action, payload))


def candidate(finding_id: str = "f-1") -> Finding:
    return Finding(
        finding_id=finding_id,
        evidence_group_id="eg-1",
        rule_code="AR-041",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
    )


def test_confirm_records_decision_and_counts_as_violation() -> None:
    result = review(candidate(), actor=INSPECTOR, action="CONFIRM", comment=COMMENT)
    assert result.finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert result.inspector_decision is not None
    assert result.inspector_decision.comment == COMMENT
    assert result.counts_as_violation


def test_confirm_without_comment_is_refused() -> None:
    with pytest.raises(TransitionError, match="comment"):
        review(candidate(), actor=INSPECTOR, action="CONFIRM")


def test_reject_without_reason_code_is_refused() -> None:
    with pytest.raises(TransitionError):
        review(candidate(), actor=INSPECTOR, action="REJECT", comment=COMMENT)


def test_reject_with_reason_code() -> None:
    result = review(
        candidate(),
        actor=INSPECTOR,
        action="REJECT",
        reason_code=ReasonCode.OCR_ERROR,
        comment="OCR прочитал B30 вместо B35.",
    )
    assert result.finding_status is FindingStatus.NEGATIVE_VERIFIED
    assert not result.counts_as_violation


def test_automation_cannot_review() -> None:
    with pytest.raises(TransitionError):
        review(
            candidate(),
            actor=Actor("worker", is_human=False),
            action="CONFIRM",
            comment=COMMENT,
        )


def test_finalize_blocked_by_open_candidate() -> None:
    ok, pending = can_finalize([candidate("f-1")])
    assert not ok
    assert pending == ["f-1"]


def test_suspicion_blocks_finalize() -> None:
    stalled = replace(candidate("f-s"), finding_status=FindingStatus.SUSPICION)
    ok, pending = can_finalize([stalled])
    assert not ok
    assert pending == ["f-s"]


def test_clarification_does_not_block_finalize() -> None:
    stalled = replace(candidate("f-c"), finding_status=FindingStatus.CLARIFICATION_REQUIRED)
    ok, pending = can_finalize([stalled])
    assert ok
    assert pending == []


def test_split_is_not_an_atomic_review_action() -> None:
    with pytest.raises(TransitionError, match="SPLIT"):
        review(candidate(), actor=INSPECTOR, action="SPLIT", comment=COMMENT)


def test_split_is_unimplemented_until_each_part_has_evidence() -> None:
    with pytest.raises(NotImplementedError, match="evidence_group"):
        split(candidate(), parts=2)


def test_inspector_can_select_unknown_stamp_as_etalon() -> None:
    status = select_revision_as_etalon(
        actor=INSPECTOR,
        stamp=ApprovalStatus.UNKNOWN,
        comment="В комплекте организатора это утверждённый том ПД.",
    )
    assert status is ApprovalStatus.APPROVED


def test_machine_cannot_select_revision() -> None:
    with pytest.raises(TransitionError, match="инспектора"):
        select_revision_as_etalon(
            actor=Actor("worker", is_human=False),
            stamp=ApprovalStatus.UNKNOWN,
            comment="нельзя",
        )


def test_not_approved_stamp_cannot_be_selected() -> None:
    with pytest.raises(TransitionError, match="отказ"):
        select_revision_as_etalon(
            actor=INSPECTOR,
            stamp=ApprovalStatus.NOT_APPROVED,
            comment="черновик",
        )


def test_select_revision_requires_comment() -> None:
    with pytest.raises(TransitionError, match="comment"):
        select_revision_as_etalon(
            actor=INSPECTOR,
            stamp=ApprovalStatus.UNKNOWN,
            comment="   ",
        )



def test_missing_evidence_does_not_block_finalize() -> None:
    stalled = replace(candidate("f-2"), finding_status=FindingStatus.MISSING_EVIDENCE)
    ok, pending = can_finalize([stalled])
    assert ok
    assert pending == []


def test_start_verification_requires_human() -> None:
    audit = MemoryAudit()
    with pytest.raises(TransitionError, match="human"):
        start_verification(
            ProcessState.READY,
            actor=Actor("worker", is_human=False),
            audit=audit,
        )
    target = start_verification(ProcessState.READY, actor=INSPECTOR, audit=audit)
    assert target is ProcessState.VERIFYING
    assert audit.records[0][1] == "START_VERIFICATION"


def test_complete_verification_blocked_by_candidate() -> None:
    audit = MemoryAudit()
    with pytest.raises(TransitionError, match="unprocessed"):
        complete_verification(
            ProcessState.VERIFYING,
            actor=INSPECTOR,
            findings=[candidate("f-1")],
            audit=audit,
        )


def test_complete_verification_does_not_finalize() -> None:
    audit = MemoryAudit()
    target = complete_verification(
        ProcessState.VERIFYING,
        actor=INSPECTOR,
        findings=[],
        audit=audit,
    )
    assert target is ProcessState.COMPLETED
    assert audit.records[0][1] == "COMPLETE_VERIFICATION"


def test_finalize_from_ready_is_refused() -> None:
    audit = MemoryAudit()
    with pytest.raises(TransitionError, match="READY"):
        finalize_process(
            ProcessState.READY,
            actor=INSPECTOR,
            findings=[],
            audit=audit,
        )


def test_finalize_process_requires_human_and_audit() -> None:
    audit = MemoryAudit()
    with pytest.raises(TransitionError, match="human"):
        finalize_process(
            ProcessState.COMPLETED,
            actor=Actor("worker", is_human=False),
            findings=[],
            audit=audit,
        )
    target = finalize_process(
        ProcessState.COMPLETED,
        actor=INSPECTOR,
        findings=[],
        audit=audit,
    )
    assert target is ProcessState.FINALIZED
    assert audit.records[0][:2] == ("inspector-1", "FINALIZE")


def test_machine_cannot_finalize_via_state_machine() -> None:
    from kontur.domain.state_machines import advance_process

    with pytest.raises(TransitionError, match="finalize_process"):
        advance_process(ProcessState.COMPLETED, ProcessState.FINALIZED)


def test_unfinalize_process_writes_audit() -> None:
    audit = MemoryAudit()
    target = unfinalize_process(
        ProcessState.FINALIZED,
        actor=SUPERVISOR,
        reason="ошибка комплекта",
        audit=audit,
    )
    assert target is ProcessState.COMPLETED
    assert audit.records[0][1] == "UNFINALIZE"
    assert audit.records[0][2]["reason"] == "ошибка комплекта"
