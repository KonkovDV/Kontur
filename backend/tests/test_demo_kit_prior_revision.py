"""Черновик учебного комплекта как предыдущая редакция эталона (только для diff)."""

from __future__ import annotations

from pdf_fixtures import contest_slice_font

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.state_machines import Actor
from kontur.domain.statuses import FindingStatus
from kontur.evaluation.demo_kit import (
    DEMO_OBJECT_ID,
    DRAFT_FILE_ID,
    ETALON_FILE_ID,
    install_demo_kit,
)

assert contest_slice_font() is not None


def _files(record):  # type: ignore[no-untyped-def]
    return {item.file_id: item for item in record.files}


def test_declared_predecessor_is_not_used_before_the_inspector_selects() -> None:
    workspace = ProcessWorkspace()
    record = install_demo_kit(workspace, DEMO_OBJECT_ID)
    files = _files(record)
    assert files[ETALON_FILE_ID].declared_predecessor_file_id == DRAFT_FILE_ID
    assert files[ETALON_FILE_ID].predecessor_file_id is None
    assert files[DRAFT_FILE_ID].successor_file_id is None
    assert all(not g.prior_revision_fragments for g in record.evidence_groups.values())


def test_selection_links_draft_and_keeps_it_out_of_findings() -> None:
    workspace = ProcessWorkspace()
    record = install_demo_kit(workspace, DEMO_OBJECT_ID)
    record = workspace.select_revision(
        record.process_id,
        ETALON_FILE_ID,
        actor=Actor(actor_id="insp", is_human=True),
        comment="Утверждённая редакция.",
    )
    files = _files(record)
    assert files[ETALON_FILE_ID].predecessor_file_id == DRAFT_FILE_ID
    assert files[DRAFT_FILE_ID].successor_file_id == ETALON_FILE_ID
    with_prior = [g for g in record.evidence_groups.values() if g.prior_revision_fragments]
    assert with_prior
    for group in with_prior:
        assert {f.document.file_id for f in group.fragments}.isdisjoint({DRAFT_FILE_ID})
        assert {f.document.file_id for f in group.prior_revision_fragments} == {DRAFT_FILE_ID}
        draft = next(r for r in group.resolved_revisions if r.file_id == DRAFT_FILE_ID)
        assert draft.successor_file_id == ETALON_FILE_ID
        assert draft.approval_basis.value != "INSPECTOR_SELECT"
    assert FindingStatus.CANDIDATE in {f.finding_status for f in record.findings.values()}
