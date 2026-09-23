"""E2E конкурсного среза PZ-001 / KR-055 / AR-041 / IOS4-078 / IOS4-079.

Фикстуры + пайплайн на векторном PDF. Не TEST_HIDDEN, не закрытие гейта J.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pdf_fixtures import contest_slice_font, cyrillic_pdf

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken, extract_number
from kontur.application.process_pipeline import (
    PipelineFile,
    _pages_from_blobs,
    run_process_pipeline,
)
from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState
from kontur.evaluation.contest_slice import (
    CONTEST_SLICE_CODES,
    contest_findings,
    contest_run_log,
    groups_by_rule,
)
from kontur.infrastructure.matrix.registry import FileRuleRegistry
from kontur.infrastructure.pdfium_tokens import file_sha256

OBJECT_ID = "OBJ-CONTEST-SLICE-E2E"
HASH = "c" * 64
_REGISTRY = FileRuleRegistry()
_FONT = contest_slice_font()
needs_font = pytest.mark.skipif(_FONT is None, reason="нет TTF с кириллицей")

_STAMP = (("Утвердил", 20.0, 20.0), ("Иванов И.И.", 90.0, 20.0))
_LABEL_X = 20.0
_VALUE_X = 200.0
# Значение чуть ниже подписи (user Y вверх): иначе глиф числа выше и
# reading_key ставит число до якоря → окно dual-read схлопывает всю страницу.
_VALUE_DY = -4.0
_ROWS: tuple[tuple[str, float], ...] = (
    ("Площадь застройки", 210.0),
    ("Класс бетона", 190.0),
    ("Ширина проема", 170.0),
    ("сечение воздуховода", 150.0),
    ("приточная установка", 130.0),
)


def _tok(text: str, x: float, y: float) -> PageToken:
    polygon = ((x, y), (x + 0.12, y), (x + 0.12, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _line(*words: str, y: float) -> tuple[PageToken, ...]:
    return tuple(_tok(word, 0.05 + index * 0.16, y) for index, word in enumerate(words))


def _doc(stage: DocStage, *, approved: bool = True) -> DocumentRef:
    return DocumentRef(
        file_id=f"slice-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"SLICE-{stage.value}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.UNKNOWN,
        sheet="ОД",
    )


def _completeness(*, rd: Completeness = Completeness.UPLOADED) -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: rd,
        DocStage.ID: Completeness.MISSING,
    }


def _value_row(y: float, label: str, *values: str) -> tuple[PageToken, ...]:
    return _line(label, *values, y=y)


def _pages(
    pd_values: Sequence[tuple[str, str]],
    rd_values: Sequence[tuple[str, str]] | None,
    *,
    approved: bool = True,
) -> dict[DocStage, StagePage]:
    pd_tokens: list[PageToken] = []
    for index, (label, value) in enumerate(pd_values):
        pd_tokens.extend(_value_row(0.20 + index * 0.12, label, value))
    pages = {
        DocStage.PD: StagePage(document=_doc(DocStage.PD, approved=approved), tokens=tuple(pd_tokens))
    }
    if rd_values is not None:
        rd_tokens: list[PageToken] = []
        for index, (label, value) in enumerate(rd_values):
            rd_tokens.extend(_value_row(0.20 + index * 0.12, label, value))
        pages[DocStage.RD] = StagePage(
            document=_doc(DocStage.RD, approved=approved), tokens=tuple(rd_tokens)
        )
    return pages


_PD_VALUES: tuple[tuple[str, str], ...] = (
    ("Площадь застройки", "1250,5"),
    ("Класс бетона", "B30"),
    ("Ширина проема", "1,2"),
    ("сечение воздуховода", "500×300"),
    ("приточная установка", "1000 м³/ч"),
)
_RD_CANDIDATE: tuple[tuple[str, str], ...] = (
    ("Площадь застройки", "1100"),
    ("Класс бетона", "B25"),
    ("Ширина проема", "0,8"),
    ("сечение воздуховода", "400×200"),
    ("приточная установка", "800 м³/ч"),
)


def _with_width(rows: Sequence[tuple[str, str]], width: str) -> tuple[tuple[str, str], ...]:
    return tuple((label, width if label == "Ширина проема" else value) for label, value in rows)


def test_contest_codes_are_executable() -> None:
    for code in CONTEST_SLICE_CODES:
        assert _REGISTRY.get(code)["coverage"] == "executable"


def test_token_slice_candidates_have_evidence() -> None:
    pages = _pages(_PD_VALUES, _RD_CANDIDATE)
    findings = []
    groups = []
    for code in CONTEST_SLICE_CODES:
        result = evaluate_rule(
            _REGISTRY.get(code),
            object_id=OBJECT_ID,
            pages=pages,
            completeness=_completeness(),
        )
        findings.append(result.finding)
        if result.evidence_group is not None:
            groups.append(result.evidence_group)
        assert result.finding.finding_status is FindingStatus.CANDIDATE
    log = contest_run_log(object_id=OBJECT_ID, findings=findings, groups=groups)
    assert [row["rule_code"] for row in log] == list(CONTEST_SLICE_CODES)
    for row in log:
        assert row["closes_gate_j"] is False
        assert row["fragments"]


def test_token_slice_missing_rd_is_missing_evidence() -> None:
    pages = _pages(_PD_VALUES, None)
    for code in CONTEST_SLICE_CODES:
        result = evaluate_rule(
            _REGISTRY.get(code),
            object_id=OBJECT_ID,
            pages=pages,
            completeness=_completeness(rd=Completeness.MISSING),
        )
        assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
        assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        assert result.finding.evidence_group_id is None


def test_token_slice_unapproved_is_clarification() -> None:
    pages = _pages(_PD_VALUES, _RD_CANDIDATE, approved=False)
    for code in CONTEST_SLICE_CODES:
        result = evaluate_rule(
            _REGISTRY.get(code),
            object_id=OBJECT_ID,
            pages=pages,
            completeness=_completeness(),
        )
        assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
        assert result.finding.finding_status is not FindingStatus.CANDIDATE


def test_token_slice_no_anchor_is_low_quality() -> None:
    pages = {
        DocStage.PD: StagePage(document=_doc(DocStage.PD), tokens=_line("Таблица", "прочее", y=0.3)),
        DocStage.RD: StagePage(document=_doc(DocStage.RD), tokens=_line("Таблица", "прочее", y=0.3)),
    }
    for code in CONTEST_SLICE_CODES:
        result = evaluate_rule(
            _REGISTRY.get(code),
            object_id=OBJECT_ID,
            pages=pages,
            completeness=_completeness(),
        )
        assert result.finding.finding_status is FindingStatus.LOW_QUALITY
        assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def _sheet(values: Sequence[tuple[str, str]], *, stamp: bool = True) -> bytes:
    lines: list[tuple[str, float, float]] = []
    if stamp:
        lines.extend(_STAMP)
    for (label, _), (_, y) in zip(values, _ROWS, strict=True):
        lines.append((label, _LABEL_X, y))
    for (_, value), (_, y) in zip(values, _ROWS, strict=True):
        lines.append((value, _VALUE_X, y + _VALUE_DY))
    return cyrillic_pdf(lines)


def _pipeline(pd: bytes, rd: bytes | None) -> object:
    files = [
        PipelineFile("f-pd", file_sha256(pd), "pd.pdf", DocStage.PD),
    ]
    blobs = {"f-pd": pd}
    completeness = _completeness(rd=Completeness.MISSING if rd is None else Completeness.UPLOADED)
    if rd is not None:
        files.append(PipelineFile("f-rd", file_sha256(rd), "rd.pdf", DocStage.RD))
        blobs["f-rd"] = rd
    return run_process_pipeline(
        object_id=OBJECT_ID,
        completeness=completeness,
        files=tuple(files),
        blobs=blobs,
    )


@needs_font
def test_pdf_pipeline_detects_five_candidates() -> None:
    report = _pipeline(_sheet(_PD_VALUES), _sheet(_RD_CANDIDATE))
    assert report.parse_errors == ()
    assert report.stamp_by_file_id["f-pd"] is ApprovalStatus.APPROVED
    assert report.stamp_by_file_id["f-rd"] is ApprovalStatus.APPROVED
    slice_findings = contest_findings(report.findings)
    grouped = groups_by_rule(report.evidence_groups)
    for code in CONTEST_SLICE_CODES:
        finding = slice_findings[code]
        assert finding.finding_status is FindingStatus.CANDIDATE
        assert finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    log = contest_run_log(
        object_id=OBJECT_ID,
        findings=tuple(slice_findings.values()),
        groups=tuple(grouped[code] for code in CONTEST_SLICE_CODES),
    )
    assert all(row["fragments"][0]["file_hash"] for row in log)
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        item.finding_status for item in report.findings
    }


@needs_font
def test_pdf_pipeline_missing_rd_is_not_violation() -> None:
    report = _pipeline(_sheet(_PD_VALUES), None)
    for finding in contest_findings(report.findings).values():
        assert finding.finding_status is FindingStatus.MISSING_EVIDENCE


@needs_font
def test_pdf_pipeline_ar041_mm_equals_metres_after_conversion() -> None:
    """1200 мм и 1,2 м на векторном PDF — одно значение в метрах, не угадка голого 1200."""

    report = _pipeline(
        _sheet(_with_width(_PD_VALUES, "1200 мм")),
        _sheet(_with_width(_PD_VALUES, "1,2 м")),
    )
    finding = contest_findings(report.findings)["AR-041"]
    assert finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert finding.actual_value == pytest.approx(1.2)
    assert finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


@needs_font
def test_pdf_pipeline_ar041_899mm_is_candidate_not_bare_guess() -> None:
    report = _pipeline(
        _sheet(_with_width(_PD_VALUES, "1200 мм")),
        _sheet(_with_width(_PD_VALUES, "899 мм")),
    )
    finding = contest_findings(report.findings)["AR-041"]
    assert finding.finding_status is FindingStatus.CANDIDATE
    assert finding.actual_value == pytest.approx(0.899)
    assert finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


@needs_font
def test_pdf_pipeline_ar041_bare_1200_stays_unconverted() -> None:
    pd = _sheet(_with_width(_PD_VALUES, "1200"))
    item = PipelineFile("f-pd", file_sha256(pd), "pd.pdf", DocStage.PD)
    pages, errors, _stamps, _clean, _pool = _pages_from_blobs((item,), {"f-pd": pd})
    assert errors == ()
    page = pages[DocStage.PD]
    tokens = page[0].tokens if isinstance(page, tuple) else page.tokens
    hit = extract_number(tokens, _REGISTRY.get("AR-041"))
    assert hit is not None
    assert hit.extraction.normalized_value == 1200.0


@needs_font
def test_pdf_pipeline_without_stamp_still_compares() -> None:
    """Одна ПД без штампа — эталон комплекта, не остановка на L4."""

    report = _pipeline(_sheet(_PD_VALUES, stamp=False), _sheet(_RD_CANDIDATE, stamp=False))
    assert report.stamp_by_file_id["f-pd"] is ApprovalStatus.UNKNOWN
    for finding in contest_findings(report.findings).values():
        assert finding.finding_status is FindingStatus.CANDIDATE
        assert finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


@needs_font
def test_workspace_pipeline_stays_ready_without_human_verdict() -> None:
    pd = _sheet(_PD_VALUES)
    rd = _sheet(_RD_CANDIDATE)
    workspace = ProcessWorkspace()
    record = workspace.create(OBJECT_ID, _completeness())
    for file_id, stage, payload in (("f-pd", DocStage.PD, pd), ("f-rd", DocStage.RD, rd)):
        item = AcceptedFile(
            file_id=file_id,
            file_hash=file_sha256(payload),
            filename=f"{stage.value.lower()}.pdf",
            doc_stage=stage,
            size_bytes=len(payload),
        )
        workspace.attach_file(record, item)
        workspace.keep_blob(record, file_id, payload)
    workspace.run_matrix_pipeline(record)
    assert record.process_state is ProcessState.READY
    slice_findings = contest_findings(tuple(record.findings.values()))
    for finding in slice_findings.values():
        assert finding.finding_status is FindingStatus.CANDIDATE
        assert finding.evidence_group_id is not None
        assert finding.source_id
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in record.findings.values()
    )
