"""Верификация инспектором: атомарность, обязательная причина, финализация."""

from __future__ import annotations

from dataclasses import replace

import pytest

from kontur.application.review import (
    can_finalize,
    complete_verification,
    confirm_candidates,
    finalize_process,
    review,
    select_revision_as_etalon,
    split,
    start_verification,
    unfinalize_process,
)
from kontur.domain.models import (
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Extraction,
    ExtractionEngine,
    Finding,
)
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


def test_mass_confirm_only_candidates_and_refuses_the_whole_batch() -> None:
    first = candidate("f-1")
    second = candidate("f-2")
    second = replace(second, evidence_group_id="eg-2")
    suspicion = replace(
        candidate("f-3"),
        finding_status=FindingStatus.SUSPICION,
        evidence_group_id="eg-3",
    )
    missing = replace(
        candidate("f-4"),
        finding_status=FindingStatus.MISSING_EVIDENCE,
        evidence_group_id=None,
    )
    confirmed = confirm_candidates((first, second), actor=INSPECTOR, comment=COMMENT)
    assert [item.finding_status for item in confirmed] == [
        FindingStatus.CONFIRMED_VIOLATION,
        FindingStatus.CONFIRMED_VIOLATION,
    ]
    assert first.finding_status is FindingStatus.CANDIDATE
    for bad in (
        (),
        (first, first),
        (first, suspicion),
        (missing,),
        (first, missing),
    ):
        with pytest.raises(TransitionError):
            confirm_candidates(bad, actor=INSPECTOR, comment=COMMENT)
    machine = Actor("pipeline", is_human=False)
    with pytest.raises(TransitionError, match="инспектора"):
        confirm_candidates((candidate("f-9"),), actor=machine, comment=COMMENT)


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


@pytest.mark.parametrize(
    "status",
    [
        FindingStatus.LOW_QUALITY,
        FindingStatus.ABSTAIN,
        FindingStatus.NOT_COMPARABLE,
        FindingStatus.MISSING_EVIDENCE,
    ],
)
def test_review_cannot_turn_a_quality_refusal_into_a_verdict(status: FindingStatus) -> None:
    """RT-2609-29: решение инспектора не делает отказ нарушением или «пройдено»."""

    refused = replace(candidate(), finding_status=status)
    with pytest.raises(TransitionError):
        review(refused, actor=INSPECTOR, action="CONFIRM", comment=COMMENT)
    with pytest.raises(TransitionError):
        review(
            refused,
            actor=INSPECTOR,
            action="REJECT",
            reason_code=ReasonCode.SOURCE_QUALITY,
            comment=COMMENT,
        )


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


def test_suspicion_does_not_block_finalize() -> None:
    stalled = replace(candidate("f-s"), finding_status=FindingStatus.SUSPICION)
    ok, pending = can_finalize([stalled])
    assert ok
    assert pending == []


def test_inspector_can_accept_or_reject_a_hypothesis() -> None:
    suspicion = replace(candidate("f-s"), finding_status=FindingStatus.SUSPICION)
    accepted = review(suspicion, actor=INSPECTOR, action="CONFIRM", comment=COMMENT)
    assert accepted.finding_status is FindingStatus.CONFIRMED_VIOLATION
    rejected = review(
        suspicion,
        actor=INSPECTOR,
        action="REJECT",
        reason_code=ReasonCode.SOURCE_QUALITY,
        comment=COMMENT,
    )
    assert rejected.finding_status is FindingStatus.NEGATIVE_VERIFIED


def test_machine_cannot_accept_a_hypothesis() -> None:
    suspicion = replace(candidate("f-s"), finding_status=FindingStatus.SUSPICION)
    with pytest.raises(TransitionError):
        review(
            suspicion,
            actor=Actor("worker", is_human=False),
            action="CONFIRM",
            comment=COMMENT,
        )


def test_clarification_does_not_block_finalize() -> None:
    stalled = replace(candidate("f-c"), finding_status=FindingStatus.CLARIFICATION_REQUIRED)
    ok, pending = can_finalize([stalled])
    assert ok
    assert pending == []


def test_split_is_not_an_atomic_review_action() -> None:
    with pytest.raises(TransitionError, match="SPLIT"):
        review(candidate(), actor=INSPECTOR, action="SPLIT", comment=COMMENT)


def _part(group_id: str, rule_code: str = "AR-041") -> EvidenceGroup:
    square = ((0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2))
    document = DocumentRef(
        file_id=f"file-{group_id}",
        file_hash="a" * 64,
        doc_stage=DocStage.PD,
        document_code="AR-1",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )

    def fragment(role: EvidenceRole) -> EvidenceFragment:
        return EvidenceFragment(
            fragment_id=f"{group_id}-{role.value}",
            role=role,
            document=document,
            page=1,
            polygon_source=square,
            polygon_norm=square,
            extracted=Extraction(
                raw_token="десять",  # noqa: S106
                engine=ExtractionEngine.VECTOR,
                engine_version="test",
                confidence=0.99,
                normalized_value=10.0,
                grounded_in_source_tokens=True,
                second_read_agrees=True,
            ),
        )

    return EvidenceGroup(
        evidence_group_id=group_id,
        object_id="obj-1",
        rule_code=rule_code,
        matrix_version="draft-0",
        fragments=(fragment(EvidenceRole.EXPECTED), fragment(EvidenceRole.ACTUAL)),
    )


def test_inspector_splits_a_candidate_into_parts_with_their_own_evidence() -> None:
    parts = split(
        candidate(),
        (_part("eg-a"), _part("eg-b")),
        actor=INSPECTOR,
    )
    assert [item.finding_id for item in parts] == ["f-1:1", "f-1:2"]
    assert [item.evidence_group_id for item in parts] == ["eg-a", "eg-b"]
    assert all(item.finding_status is FindingStatus.CANDIDATE for item in parts)
    assert all(item.finding_status is not FindingStatus.CONFIRMED_VIOLATION for item in parts)


def test_machine_cannot_split_a_finding() -> None:
    with pytest.raises(TransitionError, match="инспектора"):
        split(candidate(), (_part("eg-a"), _part("eg-b")), actor=Actor("worker", is_human=False))


def test_split_refuses_a_part_without_a_distinct_evidence_group() -> None:
    with pytest.raises(TransitionError, match="evidence_group_id"):
        split(candidate(), (_part("eg-a"), _part("eg-a")), actor=INSPECTOR)


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
