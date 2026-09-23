"""Обмер пары штрихов через evaluate. Живое IOS4-078 остаётся number."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame
from kontur.domain.geometry import polygon_in_unit_square
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.evaluation.train_public import is_predicted_positive
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "e" * 64
FRAME = PageFrame(media=(0.0, 0.0, 200.0, 200.0), crop=(0.0, 0.0, 200.0, 200.0), rotate=0)


def _rule() -> dict[str, object]:
    return {
        "code": "IOS4-078",
        "matrix_version": "draft-0",
        "unit": "мм",
        "coverage": "executable",
        "review_priority": "HIGH",
        "applicability": {"stages_required": ["PD", "RD"]},
        "extractor": {"type": "geometry", "dual_read_required": True},
        "comparator": {"operator": "ge", "rounding": "none"},
        "failure_mapping": {
            "source_absent": "MISSING_EVIDENCE",
            "low_quality": "LOW_QUALITY",
            "reads_disagree": "ABSTAIN",
            "revision_conflict": "CLARIFICATION_REQUIRED",
        },
    }


def _stamp() -> tuple[PageToken, ...]:
    tokens = []
    for text, x in (("М", 0.05), ("1:100", 0.20)):
        polygon = ((x, 0.90), (x + 0.12, 0.90), (x + 0.12, 0.94), (x, 0.94))
        tokens.append(PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon))
    return tuple(tokens)


def _lines(y0: float, y1: float) -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    for y in (y0, y1):
        path = pdfium_c.FPDFPageObj_CreateNewPath(10, y)
        pdfium_c.FPDFPath_LineTo(path, 120, y)
        pdfium_c.FPDFPath_SetDrawMode(path, 0, 1, 0)
        pdfium_c.FPDFPage_InsertObject(page, path)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _doc(stage: DocStage) -> DocumentRef:
    return DocumentRef(
        file_id=f"geom-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"OV-{stage.value}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )


def _page(stage: DocStage, data: bytes, tokens: tuple[PageToken, ...]) -> StagePage:
    return StagePage(document=_doc(stage), tokens=tokens, pdf_bytes=data, frames=(FRAME,))


def _both(pd: bytes, rd: bytes) -> dict[DocStage, StagePage]:
    return {
        DocStage.PD: _page(DocStage.PD, pd, _stamp()),
        DocStage.RD: _page(DocStage.RD, rd, _stamp()),
    }


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def test_equal_ducts_are_not_a_hit() -> None:
    data = _lines(40, 52)
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-GEOM",
        pages=_both(data, data),
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert is_predicted_positive(result.finding.finding_status) is False
    assert result.evidence_group is not None
    for fragment in result.evidence_group.fragments:
        assert fragment.document.file_hash == HASH
        assert fragment.page == 1
        assert polygon_in_unit_square(fragment.polygon_norm)


def test_narrower_rd_is_a_candidate_with_evidence() -> None:
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-GEOM",
        pages=_both(_lines(40, 52), _lines(40, 48)),
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert is_predicted_positive(result.finding.finding_status) is True
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    group = result.evidence_group
    assert group is not None
    assert result.finding.evidence_group_id == group.evidence_group_id
    assert len(group.fragments) == 2


def test_missing_scale_is_low_quality() -> None:
    drawing = ((0.10, 0.40), (0.30, 0.40), (0.30, 0.44), (0.10, 0.44))
    token = PageToken(text="план", page=1, polygon_source=drawing, polygon_norm=drawing)
    data = _lines(40, 52)
    pages = {
        DocStage.PD: _page(DocStage.PD, data, (token,)),
        DocStage.RD: _page(DocStage.RD, data, _stamp()),
    }
    result = evaluate_rule(
        _rule(), object_id="OBJ-GEOM", pages=pages, completeness=_completeness()
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert "масштаб" in result.finding.rationale
    assert is_predicted_positive(result.finding.finding_status) is False


def test_missing_rd_is_missing_evidence() -> None:
    result = evaluate_rule(
        _rule(),
        object_id="OBJ-GEOM",
        pages={},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.evidence_group is None


def test_unknown_drawing_type_is_not_executed() -> None:
    rule = _rule()
    extractor = rule["extractor"]
    assert isinstance(extractor, dict)
    extractor["type"] = "drawing_dimension"
    result = evaluate_rule(
        rule,
        object_id="OBJ-GEOM",
        pages=_both(_lines(40, 52), _lines(40, 52)),
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED


def test_live_ios4_rule_stays_number() -> None:
    rule = FileRuleRegistry(REPO / "data" / "matrix").get("IOS4-078")
    extractor = rule["extractor"]
    assert isinstance(extractor, dict)
    assert extractor["type"] == "number"
    assert rule["coverage"] == "executable"


def test_geometry_params_match_the_contract() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = REPO / "contracts" / "schemas" / "rule.schema.json"
    rule_path = REPO / "data" / "matrix" / "rules" / "IOS4-078.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = json.loads(rule_path.read_text(encoding="utf-8"))
    sample["extractor"]["type"] = "geometry"
    sample["extractor"]["geometry_params"] = {
        "angle_deg": 2,
        "min_overlap": 0.6,
        "min_length_pt": 20,
        "gap_min_pt": 2,
        "gap_max_pt": 60,
        "stamp_y": 0.85,
        "read_tolerance_rel": 0.02,
    }
    jsonschema.validate(sample, schema)
    sample["extractor"]["geometry_params"]["tuned_on_gold"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(sample, schema)
