"""Списки марок систем и отказ сравнивать файл с самим собой."""

from __future__ import annotations

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.element_table import parse_element_table
from kontur.application.extractors.number import PageToken
from kontur.application.system_marks import expand_system_marks
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry


def _token(text: str, x: float, y: float = 0.4) -> PageToken:
    polygon = ((x, y), (x + 0.08, y), (x + 0.08, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def test_list_and_range_become_separate_marks() -> None:
    assert expand_system_marks("B2.7, 8, 9") == ("В2.7", "В2.8", "В2.9")
    assert expand_system_marks("В2.7, В2.8, В2.9") == ("В2.7", "В2.8", "В2.9")
    assert expand_system_marks("В2.4-В2.6") == ("В2.4", "В2.5", "В2.6")
    assert expand_system_marks("В2.4-П2.6") == ()


def test_grille_size_is_not_a_system_mark() -> None:
    assert expand_system_marks("П300*300") == ()
    assert expand_system_marks("В") == ()


def test_table_row_splits_a_mark_list() -> None:
    rows = parse_element_table(
        (
            _token("В2.7,8,9", 0.1),
            _token("125", 0.4),
        )
    )
    assert isinstance(rows, dict)
    assert set(rows) == {"В2.7", "В2.8", "В2.9"}
    assert rows["В2.8"].value == 125


def test_one_file_on_both_stages_is_not_a_design_change() -> None:
    rule = FileRuleRegistry().get("PZ-001")
    shared = DocumentRef(
        file_id="same-volume",
        file_hash="a" * 64,
        doc_stage=DocStage.PD,
        document_code="PZ",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )
    other = DocumentRef(
        file_id="same-volume",
        file_hash="b" * 64,
        doc_stage=DocStage.RD,
        document_code="PZ",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )

    def page(document: DocumentRef, value: str) -> StagePage:
        return StagePage(
            document=document,
            tokens=(
                _token("Площадь", 0.05),
                _token("застройки", 0.2),
                _token(value, 0.4),
            ),
        )

    result = evaluate_rule(
        rule,
        object_id="OBJ-1",
        pages={DocStage.PD: page(shared, "1250,5"), DocStage.RD: page(other, "1100")},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.UPLOADED,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.NOT_COMPARABLE
    assert "один файл" in result.finding.rationale
