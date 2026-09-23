"""Репетиция демо #78: ПД/РД/ИД, stale PD, три CANDIDATE, review, protocol, outbox.

Синтетические векторные PDF. Не Polar, не TEST_HIDDEN, не закрытие гейта K.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from pdf_fixtures import contest_slice_font, cyrillic_pdf

from kontur.application.process_pipeline import PipelineFile, run_process_pipeline
from kontur.application.protocol import protocol_for_http
from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import ApprovalStatus, DocStage
from kontur.domain.state_machines import Actor
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState, ReasonCode
from kontur.evaluation.contest_slice import assert_contest_honest, groups_by_rule
from kontur.evaluation.demo_cold_start import (
    CLOSES_GATE_J,
    CLOSES_GATE_K,
    COMPOSE_DEMO_SERVICES,
    DEMO_CODES,
    DEMO_OBJECT_ID,
    assert_honest_coverage,
    candidate_codes,
    demo_findings,
)
from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.matrix.registry import FileRuleRegistry
from kontur.infrastructure.pdfium_tokens import file_sha256

_FONT = contest_slice_font()
needs_font = pytest.mark.skipif(_FONT is None, reason="нет TTF с кириллицей")
INSPECTOR = Actor("inspector-1", is_human=True)
REPO = Path(__file__).resolve().parents[2]

_STAMP = (("Утвердил", 20.0, 20.0), ("Иванов И.И.", 90.0, 20.0))
_LABEL_X = 20.0
_VALUE_X = 200.0
_VALUE_DY = -4.0
_ROWS: tuple[tuple[str, float], ...] = (
    ("Площадь застройки", 210.0),
    ("Класс бетона", 190.0),
    ("Ширина проема", 170.0),
)
_PD_VALUES: tuple[tuple[str, str], ...] = (
    ("Площадь застройки", "1250,5"),
    ("Класс бетона", "B30"),
    ("Ширина проема", "1,2"),
)
_RD_VALUES: tuple[tuple[str, str], ...] = (
    ("Площадь застройки", "1100"),
    ("Класс бетона", "B25"),
    ("Ширина проема", "0,8"),
)
_STALE_VALUES: tuple[tuple[str, str], ...] = (
    ("Площадь застройки", "9999"),
    ("Класс бетона", "B10"),
    ("Ширина проема", "0,4"),
)


def _completeness(*, with_id: bool = False) -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.UPLOADED if with_id else Completeness.MISSING,
    }


def _sheet(values: Sequence[tuple[str, str]], *, stamp: bool = True) -> bytes:
    lines: list[tuple[str, float, float]] = []
    if stamp:
        lines.extend(_STAMP)
    for (label, _), (_, y) in zip(values, _ROWS, strict=True):
        lines.append((label, _LABEL_X, y))
    for (_, value), (_, y) in zip(values, _ROWS, strict=True):
        lines.append((value, _VALUE_X, y + _VALUE_DY))
    return cyrillic_pdf(lines)


def _attach(
    workspace: ProcessWorkspace,
    record: ProcessRecord,
    file_id: str,
    stage: DocStage,
    payload: bytes,
) -> None:
    item = AcceptedFile(
        file_id=file_id,
        file_hash=file_sha256(payload),
        filename=f"{file_id}.pdf",
        doc_stage=stage,
        size_bytes=len(payload),
    )
    workspace.attach_file(record, item)
    workspace.keep_blob(record, file_id, payload)


def test_honest_coverage_is_not_132_executable() -> None:
    assert_honest_coverage(FileRuleRegistry().coverage_report())
    assert CLOSES_GATE_J is False
    assert CLOSES_GATE_K is False


def test_compose_stack_lists_demo_services() -> None:
    text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    for name in COMPOSE_DEMO_SERVICES:
        assert f"{name}:" in text, name


@needs_font
def test_unstamped_pd_compares_without_rewriting_the_stamp() -> None:
    """Одна ПД без штампа сравнивается. Штамп паспорта не становится «Утвердил»."""

    draft = _sheet(_STALE_VALUES, stamp=False)
    rd = _sheet(_RD_VALUES)
    report = run_process_pipeline(
        object_id=DEMO_OBJECT_ID,
        completeness=_completeness(),
        files=(
            PipelineFile("f-pd-draft", file_sha256(draft), "draft.pdf", DocStage.PD),
            PipelineFile("f-rd", file_sha256(rd), "rd.pdf", DocStage.RD),
        ),
        blobs={"f-pd-draft": draft, "f-rd": rd},
    )
    assert report.stamp_by_file_id["f-pd-draft"] is ApprovalStatus.UNKNOWN
    slice_findings = demo_findings(report.findings)
    assert slice_findings["PZ-001"].finding_status is FindingStatus.CANDIDATE
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in slice_findings.values()
    )
    assert all(
        "эталон без признака утверждения" not in item.rationale
        for item in slice_findings.values()
    )


@needs_font
def test_demo_rehearsal_confirm_reject_protocol_outbox() -> None:
    draft = _sheet(_STALE_VALUES, stamp=False)
    pd = _sheet(_PD_VALUES)
    rd = _sheet(_RD_VALUES)
    identity = _sheet(_PD_VALUES)
    workspace = ProcessWorkspace()
    record = workspace.create(DEMO_OBJECT_ID, _completeness(with_id=True))
    _attach(workspace, record, "f-pd-draft", DocStage.PD, draft)
    _attach(workspace, record, "f-pd", DocStage.PD, pd)
    _attach(workspace, record, "f-rd", DocStage.RD, rd)
    _attach(workspace, record, "f-id", DocStage.ID, identity)
    report = workspace.run_matrix_pipeline(record)

    assert record.process_state is ProcessState.READY
    assert report.stamp_by_file_id["f-pd-draft"] is not ApprovalStatus.APPROVED
    assert report.stamp_by_file_id["f-pd"] is ApprovalStatus.APPROVED
    assert report.stamp_by_file_id["f-rd"] is ApprovalStatus.APPROVED
    assert report.stamp_by_file_id["f-id"] is ApprovalStatus.APPROVED
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        item.finding_status for item in record.findings.values()
    }

    grouped = groups_by_rule(report.evidence_groups)
    slice_findings = demo_findings(tuple(record.findings.values()))
    for code in DEMO_CODES:
        finding = slice_findings[code]
        assert finding.finding_status is FindingStatus.CANDIDATE
        assert finding.source_id == "f-pd"
        assert finding.source_id != "f-pd-draft"
        assert_contest_honest(finding, grouped.get(code))
    assert set(candidate_codes(tuple(record.findings.values()))) == set(DEMO_CODES)

    workspace.review_finding(
        slice_findings["PZ-001"].finding_id,
        actor=INSPECTOR,
        action="CONFIRM",
        reason_code=None,
        comment="Площадь застройки в РД меньше утверждённой ПД.",
    )
    workspace.review_finding(
        slice_findings["KR-055"].finding_id,
        actor=INSPECTOR,
        action="CONFIRM",
        reason_code=None,
        comment="Класс бетона в РД понижен относительно утверждённой ПД.",
    )
    workspace.review_finding(
        slice_findings["AR-041"].finding_id,
        actor=INSPECTOR,
        action="REJECT",
        reason_code=ReasonCode.APPROVED_CHANGE_EXISTS,
        comment="Ширина проема изменена утверждённым листом, кандидат снят.",
    )

    reviewed = demo_findings(tuple(record.findings.values()))
    assert reviewed["PZ-001"].finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert reviewed["KR-055"].finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert reviewed["AR-041"].finding_status is FindingStatus.NEGATIVE_VERIFIED
    assert FindingStatus.CANDIDATE not in {
        item.finding_status for item in record.findings.values()
    }
    assert record.process_state is ProcessState.VERIFYING
    assert any(action == "REVIEW" for _actor, action, _p in record.audit.records)
    assert any(action == "START_VERIFICATION" for _a, action, _p in record.audit.records)

    workspace.complete_verification(record.process_id, INSPECTOR)
    assert record.process_state is ProcessState.COMPLETED
    workspace.finalize(record.process_id, INSPECTOR)
    assert record.process_state is ProcessState.FINALIZED
    assert record.protocol_id == f"protocol-{record.process_id}"

    store = workspace._store
    assert isinstance(store, MemoryProcessStore)
    payload = store.load_protocol(record.protocol_id)
    assert payload is not None
    wire = protocol_for_http(payload)
    assert wire["version"] == 1
    assert wire["status"] == "PROTOCOL_FINALIZED"
    sections = wire["sections"]
    assert isinstance(sections, dict)
    assert "preliminary_no_difference" not in sections
    assert "AUTO_NO_DIFFERENCE" not in str(wire)
    confirmed = sections["confirmed"]
    rejected = sections["negative_verified"]
    assert isinstance(confirmed, list) and len(confirmed) == 2
    assert isinstance(rejected, list) and len(rejected) == 1
    assert wire["violation_count"] == 2

    outbox = store._outbox[record.protocol_id]
    assert outbox["status"] == "PENDING"
    assert outbox["destination"] == "RIN"
    assert outbox["process_id"] == record.process_id
    digest = outbox["payload_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
