"""Один замкнутый контур и ведомость по маркам. Подсчёт символов сюда не входит."""

from __future__ import annotations

import io
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame
from kontur.domain.geometry import polygon_in_unit_square
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
FRAME = PageFrame(media=(0.0, 0.0, 200.0, 200.0), crop=(0.0, 0.0, 200.0, 200.0), rotate=0)


def _stamp() -> tuple[PageToken, ...]:
    tokens = []
    for text, x in (("М", 0.05), ("1:100", 0.20)):
        polygon = ((x, 0.90), (x + 0.12, 0.90), (x + 0.12, 0.94), (x, 0.94))
        tokens.append(PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon))
    return tuple(tokens)


def _rect(x: float, y: float, width: float, height: float) -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    rect = pdfium_c.FPDFPageObj_CreateNewRect(x, y, width, height)
    pdfium_c.FPDFPath_SetDrawMode(rect, 1, 1, 0)
    pdfium_c.FPDFPage_InsertObject(page, rect)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _two_rects() -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    for origin in ((20.0, 30.0), (100.0, 30.0)):
        rect = pdfium_c.FPDFPageObj_CreateNewRect(origin[0], origin[1], 40, 30)
        pdfium_c.FPDFPath_SetDrawMode(rect, 1, 1, 0)
        pdfium_c.FPDFPage_InsertObject(page, rect)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _doc(stage: DocStage, code: str, file_id: str) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=f"{file_id.encode().hex():0<64}"[:64],
        doc_stage=stage,
        document_code=code,
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )


def _page(document: DocumentRef, data: bytes) -> StagePage:
    return StagePage(document=document, tokens=_stamp(), pdf_bytes=data, frames=(FRAME,))


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def _rule(code: str) -> dict[str, object]:
    return FileRuleRegistry(REPO / "data" / "matrix").get(code)


def test_same_pavement_area_is_not_a_hit() -> None:
    data = _rect(20, 30, 80, 40)
    pd = _doc(DocStage.PD, "СПЗУ-1", "spzu-pd")
    rd = _doc(DocStage.RD, "СПЗУ-1", "spzu-rd")
    result = evaluate_rule(
        _rule("SPZU-025"),
        object_id="OBJ-SPZU-025",
        pages={DocStage.PD: _page(pd, data), DocStage.RD: _page(rd, data)},
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    group = result.evidence_group
    assert group is not None
    for fragment in group.fragments:
        assert polygon_in_unit_square(fragment.polygon_norm)


def test_much_smaller_pavement_is_a_candidate() -> None:
    pd = _doc(DocStage.PD, "СПЗУ-1", "spzu-pd")
    rd = _doc(DocStage.RD, "СПЗУ-1", "spzu-rd")
    result = evaluate_rule(
        _rule("SPZU-025"),
        object_id="OBJ-SPZU-025",
        pages={
            DocStage.PD: _page(pd, _rect(20, 30, 80, 40)),
            DocStage.RD: _page(rd, _rect(20, 30, 40, 40)),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_two_contours_are_not_summed() -> None:
    pd = _doc(DocStage.PD, "СПЗУ-1", "spzu-pd")
    rd = _doc(DocStage.RD, "СПЗУ-1", "spzu-rd")
    result = evaluate_rule(
        _rule("SPZU-026"),
        object_id="OBJ-SPZU-026",
        pages={
            DocStage.PD: _page(pd, _rect(20, 30, 80, 40)),
            DocStage.RD: _page(rd, _two_rects()),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert "несколько замкнутых" in result.finding.rationale


def _tok(text: str, x: float, y: float) -> PageToken:
    polygon = ((x, y), (x + 0.12, y), (x + 0.12, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _table_page(document: DocumentRef, rows: tuple[tuple[str, str], ...]) -> StagePage:
    tokens = list(_stamp())
    for index, (mark, value) in enumerate(rows):
        y = 0.30 + index * 0.10
        tokens.append(_tok(mark, 0.10, y))
        tokens.append(_tok(value, 0.40, y))
    return StagePage(document=document, tokens=tuple(tokens))


def test_same_riser_diameters_are_not_a_hit() -> None:
    rows = (("В1.1", "25"), ("В1.2", "32"))
    pd = _doc(DocStage.PD, "ИОС2-1", "ios2-pd")
    rd = _doc(DocStage.RD, "ИОС2-1", "ios2-rd")
    result = evaluate_rule(
        _rule("IOS2-071"),
        object_id="OBJ-IOS2-071",
        pages={
            DocStage.PD: _table_page(pd, rows),
            DocStage.RD: _table_page(rd, rows),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.evidence_group is not None


def test_smaller_riser_is_a_candidate() -> None:
    pd = _doc(DocStage.PD, "ИОС2-1", "ios2-pd")
    rd = _doc(DocStage.RD, "ИОС2-1", "ios2-rd")
    result = evaluate_rule(
        _rule("IOS2-071"),
        object_id="OBJ-IOS2-071",
        pages={
            DocStage.PD: _table_page(pd, (("В1.1", "25"), ("В1.2", "32"))),
            DocStage.RD: _table_page(rd, (("В1.1", "25"), ("В1.2", "20"))),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    group = result.evidence_group
    assert group is not None
    assert all(fragment.polygon_norm[0][1] > 0.35 for fragment in group.fragments)


def test_missing_riser_mark_is_not_paired() -> None:
    pd = _doc(DocStage.PD, "ИОС2-1", "ios2-pd")
    rd = _doc(DocStage.RD, "ИОС2-1", "ios2-rd")
    result = evaluate_rule(
        _rule("IOS2-071"),
        object_id="OBJ-IOS2-071",
        pages={
            DocStage.PD: _table_page(pd, (("В1.1", "25"), ("В1.2", "32"))),
            DocStage.RD: _table_page(rd, (("В1.1", "25"),)),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert "набор элементов" in result.finding.rationale


def test_prose_label_is_not_a_riser_row() -> None:
    pd = _doc(DocStage.PD, "ИОС2-1", "ios2-pd")
    rd = _doc(DocStage.RD, "ИОС2-1", "ios2-rd")
    rows_pd = (("Ширина проема", "1,2"),)
    rows_rd = (("Ширина проема", "0,8"),)
    result = evaluate_rule(
        _rule("IOS2-071"),
        object_id="OBJ-IOS2-071",
        pages={
            DocStage.PD: _table_page(pd, rows_pd),
            DocStage.RD: _table_page(rd, rows_rd),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert result.finding.finding_status is not FindingStatus.CANDIDATE
    result = evaluate_rule(
        _rule("SPZU-025"),
        object_id="OBJ-SPZU-025",
        pages={},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.evidence_group is None
