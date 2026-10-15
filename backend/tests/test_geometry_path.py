"""A → D1 → D0: печатное число, размер рядом, иначе MEASUREMENT_REQUIRED."""

from __future__ import annotations

from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.geometry_path import MEASUREMENT_REQUIRED
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _token(text: str, x: float, y: float) -> PageToken:
    polygon = ((x, y), (x + 0.08, y), (x + 0.08, y + 0.03), (x, y + 0.03))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _page(stage: DocStage, file_id: str, tokens: tuple[PageToken, ...]) -> StagePage:
    document = DocumentRef(
        file_id=file_id,
        file_hash="b" * 64,
        doc_stage=stage,
        document_code="АР-1",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )
    return StagePage(document=document, tokens=tokens)


def _run(code: str, pd: tuple[PageToken, ...], rd: tuple[PageToken, ...]):
    return evaluate_rule(
        REGISTRY.get(code),
        object_id="OBJ-GEOM",
        pages={
            DocStage.PD: _page(DocStage.PD, "pd", pd),
            DocStage.RD: _page(DocStage.RD, "rd", rd),
        },
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.UPLOADED,
            DocStage.ID: Completeness.MISSING,
        },
    )


def test_drawing_without_a_dimension_asks_for_measurement() -> None:
    result = _run("AR-042", (_token("Высота", 0.1, 0.2),), (_token("Высота", 0.1, 0.2),))
    assert result.finding.finding_status is FindingStatus.NOT_COMPARABLE
    assert MEASUREMENT_REQUIRED in result.finding.rationale
    assert result.finding.finding_status is not FindingStatus.CANDIDATE


def test_dimension_beside_the_label_is_compared() -> None:
    pd = (_token("Высота", 0.10, 0.20), _token("2,2 м", 0.12, 0.24))
    rd = (_token("Высота", 0.10, 0.20), _token("2,2 м", 0.12, 0.24))
    result = _run("AR-042", pd, rd)
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert REGISTRY.get("AR-042")["coverage"] == "extractor_missing"


def test_object_count_is_not_invented_from_a_nearby_number() -> None:
    tokens = (_token("лестничных", 0.10, 0.20), _token("4 шт", 0.12, 0.24))
    result = _run("AR-048", tokens, tokens)
    assert result.finding.finding_status is FindingStatus.NOT_COMPARABLE
    assert MEASUREMENT_REQUIRED in result.finding.rationale
