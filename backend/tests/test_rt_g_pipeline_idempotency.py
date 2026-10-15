"""put_finding: at-least-once retry не плодит находки (RT-G, stop-ship п. 11)."""

from __future__ import annotations

from uuid import uuid4

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import DocStage, Finding
from kontur.domain.state_machines import Actor
from kontur.domain.statuses import Completeness, FindingStatus, ReasonCode, ReviewPriority

_COMPLETENESS = {
    DocStage.PD: Completeness.UPLOADED,
    DocStage.RD: Completeness.UPLOADED,
    DocStage.ID: Completeness.MISSING,
}


def _workspace() -> tuple[ProcessWorkspace, str]:
    workspace = ProcessWorkspace()
    record = workspace.create(object_id="OBJ-TEST-001", completeness=_COMPLETENESS)
    return workspace, record.process_id


def _candidate(group_id: str) -> Finding:
    return Finding(
        finding_id=str(uuid4()),
        rule_code="TEST-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=group_id,
        rationale="тестовая находка",
    )


def _halted() -> Finding:
    return Finding(
        finding_id=str(uuid4()),
        rule_code="TEST-002",
        finding_status=FindingStatus.MISSING_EVIDENCE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=None,
        rationale="документ отсутствует",
    )


def test_repeated_put_with_same_group_id_no_duplicate() -> None:
    workspace, process_id = _workspace()
    group_id = "grp-at-least-once-001"
    first = _candidate(group_id)
    retry = _candidate(group_id)
    assert retry.finding_id != first.finding_id
    workspace.put_finding(process_id, first)
    workspace.put_finding(process_id, retry)
    record = workspace.get(process_id)
    assert record is not None
    assert len(record.findings) == 1
    stored = next(iter(record.findings.values()))
    assert stored.finding_id == retry.finding_id


def test_different_group_ids_stored_separately() -> None:
    workspace, process_id = _workspace()
    workspace.put_finding(process_id, _candidate("grp-rule-001"))
    workspace.put_finding(process_id, _candidate("grp-rule-002"))
    record = workspace.get(process_id)
    assert record is not None
    assert len(record.findings) == 2


def test_halted_finding_uses_finding_id() -> None:
    workspace, process_id = _workspace()
    halted = _halted()
    workspace.put_finding(process_id, halted)
    record = workspace.get(process_id)
    assert record is not None
    assert halted.finding_id in record.findings


def test_candidate_retries_keep_counter_at_one() -> None:
    workspace, process_id = _workspace()
    group_id = "grp-counter-test"
    for _ in range(3):
        workspace.put_finding(process_id, _candidate(group_id))
    record = workspace.get(process_id)
    assert record is not None
    assert record.to_status()["counters"]["candidates"] == 1


def test_review_updates_the_open_copy_when_finding_id_repeats() -> None:
    workspace, first_id = _workspace()
    shared = Finding(
        finding_id="pipe-PZ-001",
        evidence_group_id="eg-pz",
        rule_code="PZ-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
    )
    workspace.put_finding(first_id, shared)
    inspector = Actor(actor_id="insp-7", is_human=True)
    workspace.review_finding(
        "pipe-PZ-001",
        actor=inspector,
        action="CONFIRM",
        reason_code=None,
        comment="первая проверка",
    )
    second = workspace.create(object_id="OBJ-TEST-001", completeness=_COMPLETENESS)
    workspace.put_finding(
        second.process_id,
        Finding(
            finding_id="pipe-PZ-001",
            evidence_group_id="eg-pz",
            rule_code="PZ-001",
            finding_status=FindingStatus.CANDIDATE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        ),
    )
    updated = workspace.review_finding(
        "pipe-PZ-001",
        actor=inspector,
        action="CONFIRM",
        reason_code=None,
        comment="повторный учебный комплект",
    )
    first = workspace.get(first_id)
    opened = workspace.get(second.process_id)
    assert first is not None and opened is not None
    assert updated.finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert opened.findings["eg-pz"].finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert first.findings["eg-pz"].inspector_decision is not None
    assert first.findings["eg-pz"].inspector_decision.comment == "первая проверка"


def test_review_finds_finding_by_id_when_keyed_by_group() -> None:
    workspace, process_id = _workspace()
    finding = Finding(
        finding_id="f-1",
        evidence_group_id="eg-1",
        rule_code="PZ-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
    )
    workspace.put_finding(process_id, finding)
    updated = workspace.review_finding(
        "f-1",
        actor=Actor(actor_id="insp-7", is_human=True),
        action="REJECT",
        reason_code=ReasonCode.OCR_ERROR,
        comment="ошибка чтения",
    )
    assert updated.finding_id == "f-1"
    assert updated.finding_status is not FindingStatus.CANDIDATE


def _area(finding_id: str, actual: float) -> Finding:
    return Finding(
        finding_id=finding_id,
        evidence_group_id="eg-area",
        rule_code="PZ-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        expected_value=1250.5,
        actual_value=actual,
    )


def test_repeat_pipeline_keeps_decision_when_numbers_stay() -> None:
    workspace, process_id = _workspace()
    workspace.put_finding(process_id, _area("f-old", 1100.0))
    workspace.review_finding(
        "f-old",
        actor=Actor(actor_id="insp-7", is_human=True),
        action="CONFIRM",
        reason_code=None,
        comment="площадь в редакции меньше",
    )
    workspace.put_finding(process_id, _area("f-new", 1100.0))
    record = workspace.get(process_id)
    assert record is not None
    stored = record.findings["eg-area"]
    assert stored.finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert stored.inspector_decision is not None
    assert stored.inspector_decision.comment == "площадь в редакции меньше"


def test_repeat_pipeline_drops_decision_when_numbers_change() -> None:
    workspace, process_id = _workspace()
    workspace.put_finding(process_id, _area("f-old", 1100.0))
    workspace.review_finding(
        "f-old",
        actor=Actor(actor_id="insp-7", is_human=True),
        action="CONFIRM",
        reason_code=None,
        comment="площадь в редакции меньше",
    )
    workspace.put_finding(process_id, _area("f-new", 900.0))
    record = workspace.get(process_id)
    assert record is not None
    stored = record.findings["eg-area"]
    assert stored.finding_status is FindingStatus.CANDIDATE
    assert stored.inspector_decision is None
