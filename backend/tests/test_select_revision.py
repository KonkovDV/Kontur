"""Инспектор назначает эталон: L4 разблокируется, штамп не подменяется."""

from __future__ import annotations

from test_pdf_tokens import ascii_pdf

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import ApprovalStatus, DocStage
from kontur.domain.state_machines import Actor, TransitionError
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState
from kontur.infrastructure.pdfium_tokens import file_sha256

INSPECTOR = Actor("insp-7", is_human=True)
COMMENT = "В комплекте это последняя утверждённая редакция тома."


def _seed_completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _attach(
    workspace: ProcessWorkspace,
    record_id: str,
    *,
    file_id: str,
    stage: DocStage,
    payload: bytes,
) -> None:
    record = workspace.get(record_id)
    assert record is not None
    item = AcceptedFile(
        file_id=file_id,
        file_hash=file_sha256(payload),
        filename=f"{stage.value.lower()}.pdf",
        doc_stage=stage,
        size_bytes=len(payload),
    )
    workspace.attach_file(record, item)
    workspace.keep_blob(record, file_id, payload)


def _l4_blocked(record) -> list[str]:
    return [
        item.rule_code
        for item in record.findings.values()
        if "эталон без признака утверждения" in item.rationale
    ]


def test_package_default_unblocks_l4_without_human_verdict() -> None:
    pd = ascii_pdf("PD sheet 1")
    rd = ascii_pdf("RD sheet 1")
    workspace = ProcessWorkspace()
    record = workspace.create("obj-etalon", _seed_completeness())
    _attach(workspace, record.process_id, file_id="f-pd", stage=DocStage.PD, payload=pd)
    _attach(workspace, record.process_id, file_id="f-rd", stage=DocStage.RD, payload=rd)
    workspace.run_matrix_pipeline(record)

    assert record.process_state is ProcessState.READY
    assert record.parse_attempts == 1
    assert _l4_blocked(record) == []
    assert all(item.stamp_approval is ApprovalStatus.UNKNOWN for item in record.files)

    workspace.select_revision(record.process_id, "f-pd", actor=INSPECTOR, comment=COMMENT)
    workspace.select_revision(record.process_id, "f-rd", actor=INSPECTOR, comment=COMMENT)
    assert _l4_blocked(record) == []
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in record.findings.values()
    )
    assert record.process_state is ProcessState.READY
    actions = [action for _actor, action, _payload in record.audit.records]
    assert actions.count("SELECT_REVISION") == 2
    assert record.parse_attempts == 1


def test_select_revision_refuses_unknown_file() -> None:
    pd = ascii_pdf("PD only")
    workspace = ProcessWorkspace()
    record = workspace.create("obj-missing", _seed_completeness())
    _attach(workspace, record.process_id, file_id="f-pd", stage=DocStage.PD, payload=pd)
    workspace.run_matrix_pipeline(record)
    try:
        workspace.select_revision(
            record.process_id, "no-such-file", actor=INSPECTOR, comment=COMMENT
        )
        raise AssertionError("expected KeyError")
    except KeyError:
        pass


def test_select_revision_refuses_machine_and_non_ready() -> None:
    pd = ascii_pdf("PD sheet")
    workspace = ProcessWorkspace()
    record = workspace.create("obj-ready", _seed_completeness())
    _attach(workspace, record.process_id, file_id="f-pd", stage=DocStage.PD, payload=pd)
    workspace.run_matrix_pipeline(record)
    try:
        workspace.select_revision(
            record.process_id,
            "f-pd",
            actor=Actor("worker", is_human=False),
            comment=COMMENT,
        )
        raise AssertionError("expected TransitionError")
    except TransitionError as exc:
        assert "инспектора" in str(exc)
