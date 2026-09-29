"""AR-040 читает ширину коридора по одной паре штрихов, не по подписи."""

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
from kontur.infrastructure.duct_geometry import PT_TO_MM
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
FRAME = PageFrame(media=(0.0, 0.0, 200.0, 200.0), crop=(0.0, 0.0, 200.0, 200.0), rotate=0)
SCALE = 100


def _rule() -> dict[str, object]:
    rule = FileRuleRegistry(REPO / "data" / "matrix").get("AR-040")
    assert rule["coverage"] == "executable"
    extractor = rule["extractor"]
    assert isinstance(extractor, dict)
    assert extractor["type"] == "geometry"
    return rule


def _gap_pt(meters: float) -> float:
    return meters * 1000.0 / (PT_TO_MM * SCALE)


def _stamp() -> tuple[PageToken, ...]:
    tokens = []
    for text, x in (("М", 0.05), ("1:100", 0.20)):
        polygon = ((x, 0.90), (x + 0.12, 0.90), (x + 0.12, 0.94), (x, 0.94))
        tokens.append(PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon))
    return tuple(tokens)


def _pair(y0: float, gap: float) -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    for y in (y0, y0 + gap):
        path = pdfium_c.FPDFPageObj_CreateNewPath(10, y)
        pdfium_c.FPDFPath_LineTo(path, 120, y)
        pdfium_c.FPDFPath_SetDrawMode(path, 0, 1, 0)
        pdfium_c.FPDFPage_InsertObject(page, path)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _two_pairs(first: float, second: float) -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    for y in (20.0, 20.0 + first, 140.0, 140.0 + second):
        path = pdfium_c.FPDFPageObj_CreateNewPath(10, y)
        pdfium_c.FPDFPath_LineTo(path, 120, y)
        pdfium_c.FPDFPath_SetDrawMode(path, 0, 1, 0)
        pdfium_c.FPDFPage_InsertObject(page, path)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _doc(stage: DocStage, code: str, file_id: str) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=file_id.encode().hex().ljust(64, "0")[:64],
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


def test_corridor_at_least_1_2_m_is_not_a_hit() -> None:
    wide = _pair(40.0, _gap_pt(1.5))
    pd = _doc(DocStage.PD, "П-АР1", "ar-pd")
    rd = _doc(DocStage.RD, "П-АР1", "ar-rd")
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-AR040",
        pages={
            DocStage.PD: _page(pd, wide),
            DocStage.RD: _page(rd, wide),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    group = result.evidence_group
    assert group is not None
    assert len(group.fragments) == 2
    for fragment in group.fragments:
        assert fragment.page == 1
        assert polygon_in_unit_square(fragment.polygon_norm)


def test_narrower_than_1_2_m_is_a_candidate() -> None:
    pd = _doc(DocStage.PD, "П-АР1", "ar-pd")
    rd = _doc(DocStage.RD, "П-АР1", "ar-rd")
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-AR040",
        pages={
            DocStage.PD: _page(pd, _pair(40.0, _gap_pt(1.5))),
            DocStage.RD: _page(rd, _pair(40.0, _gap_pt(1.0))),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.evidence_group is not None


def test_two_stroke_pairs_are_not_a_guess() -> None:
    pd = _doc(DocStage.PD, "П-АР1", "ar-pd")
    rd = _doc(DocStage.RD, "П-АР1", "ar-rd")
    crowded = _two_pairs(_gap_pt(1.5), _gap_pt(1.0))
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-AR040",
        pages={
            DocStage.PD: _page(pd, _pair(40.0, _gap_pt(1.5))),
            DocStage.RD: _page(rd, crowded),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert "несколько пар" in result.finding.rationale
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_other_section_is_not_the_corridor() -> None:
    wide = _pair(40.0, _gap_pt(1.5))
    narrow = _pair(40.0, _gap_pt(1.0))
    ar_pd = _doc(DocStage.PD, "П-АР1", "ar-pd")
    kr_pd = _doc(DocStage.PD, "П-КР1", "kr-pd")
    ar_rd = _doc(DocStage.RD, "П-АР1", "ar-rd")
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-AR040",
        pages={
            DocStage.PD: (_page(ar_pd, wide), _page(kr_pd, narrow)),
            DocStage.RD: _page(ar_rd, wide),
        },
        completeness=_completeness(),
        revision_pool=[ar_pd, kr_pd, ar_rd],
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert "несколько томов" not in result.finding.rationale


def test_missing_rd_is_missing_evidence() -> None:
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-AR040",
        pages={},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.evidence_group is None
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_two_pd_of_one_cipher_are_not_compared() -> None:
    first = _doc(DocStage.PD, "П-АР1", "ar-pd-1")
    second = _doc(DocStage.PD, "П-АР1", "ar-pd-2")
    rd = _doc(DocStage.RD, "П-АР1", "ar-rd")
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-AR040",
        pages={DocStage.RD: _page(rd, _pair(40.0, _gap_pt(1.5)))},
        completeness=_completeness(),
        revision_pool=[first, second, rd],
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.finding_status is not FindingStatus.MISSING_EVIDENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.evidence_group is None
