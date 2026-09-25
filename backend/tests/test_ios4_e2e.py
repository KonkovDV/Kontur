"""E2E IOS4-078/079: number-экстрактор для золотых критических правил.

Источник правды — overrides + compile_matrix, не правка generated rules/.
IOS4-078: площадь A×B мм² на синтетике. Recall на frozen val не заявляется.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.normalize import parse_number
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, DisagreementKind, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "d" * 64
OBJECT_ID = "OBJ-IOS4-E2E"

_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    polygon = ((x, y), (x + 0.10, y), (x + 0.10, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _line(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(word, 0.05 + index * 0.13) for index, word in enumerate(words))


def _doc(stage: DocStage, suffix: str) -> DocumentRef:
    return DocumentRef(
        file_id=f"ios4-{stage.value.lower()}-{suffix}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"OV-{stage.value}-{suffix}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОВ",
    )


def _page(stage: DocStage, suffix: str, *words: str) -> StagePage:
    return StagePage(document=_doc(stage, suffix), tokens=_line(*words))


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def _completeness_no_rd() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def test_drawing_label_without_rule_number_stays_low_quality() -> None:
    """Подпись чертежа без числа правила не становится кандидатом, даже если штамп утверждён."""

    for code, pd_words, rd_words in (
        ("IOS4-078", ("Венткамера",), ("план", "ОВ")),
        (
            "IOS4-079",
            ("приточная", "установка", "П", "19"),
            ("Венткамера", "012"),
        ),
    ):
        rule = _REGISTRY.get(code)
        pages = {
            DocStage.PD: _page(DocStage.PD, code, *pd_words),
            DocStage.RD: _page(DocStage.RD, code, *rd_words),
        }
        result = evaluate_rule(
            rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness()
        )
        assert result.finding.finding_status is FindingStatus.LOW_QUALITY
        assert result.finding.finding_status is not FindingStatus.CANDIDATE
        assert result.finding.evidence_group_id is None


def test_ios4_078_is_executable() -> None:
    rule = _REGISTRY.get("IOS4-078")
    assert rule["coverage"] == "executable"
    assert rule["extractor"]["type"] == "number"
    assert rule["comparator"]["operator"] == "ge"
    assert rule["unit"] == "мм²"
    assert "multiply_dimensions" in rule["extractor"]["normalization"]


def test_ios4_078_same_section_no_difference() -> None:
    rule = _REGISTRY.get("IOS4-078")
    tokens = ("сечение воздуховода", "500×300", "мм")
    pages = {
        DocStage.PD: _page(DocStage.PD, "078-eq", *tokens),
        DocStage.RD: _page(DocStage.RD, "078-eq", *tokens),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None
    assert result.finding.has_provenance is True
    assert result.finding.source_id == pages[DocStage.PD].document.file_id
    assert result.finding.evidence_refs
    assert result.finding.expected_value == 150_000.0
    assert result.finding.actual_value == 150_000.0


def test_ios4_078_reduced_section_gives_candidate() -> None:
    rule = _REGISTRY.get("IOS4-078")
    pages = {
        DocStage.PD: _page(DocStage.PD, "078-cand", "воздуховод", "сечение", "500×300", "мм"),
        DocStage.RD: _page(DocStage.RD, "078-cand", "воздуховод", "сечение", "400×200", "мм"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.disagreement_kind is DisagreementKind.VALUE_DELTA
    assert result.finding.has_provenance is True
    assert result.finding.expected_value == 150_000.0
    assert result.finding.actual_value == 80_000.0


def test_ios4_078_larger_rd_section_no_difference() -> None:
    rule = _REGISTRY.get("IOS4-078")
    pages = {
        DocStage.PD: _page(DocStage.PD, "078-ge", "сечение воздуховода", "500×300"),
        DocStage.RD: _page(DocStage.RD, "078-ge", "воздуховод", "600×400"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_ios4_078_rd_missing() -> None:
    rule = _REGISTRY.get("IOS4-078")
    pages = {DocStage.PD: _page(DocStage.PD, "078-me", "сечение воздуховода", "500×300")}
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness_no_rd()
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.finding.evidence_group_id is None
    assert result.finding.has_provenance is False
    assert result.finding.disagreement_kind is DisagreementKind.MISSING_IN_STAGE


def test_ios4_078_dual_read_disagree_gives_abstain() -> None:
    rule = _REGISTRY.get("IOS4-078")
    pages = {
        DocStage.PD: _page(
            DocStage.PD, "078-dr", "сечение воздуховода", "500×300", "400×200"
        ),
        DocStage.RD: _page(
            DocStage.RD, "078-dr", "сечение воздуховода", "500×300", "400×200"
        ),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.ABSTAIN
    assert result.finding.evidence_group_id is None
    assert result.finding.has_provenance is False


def test_ios4_078_no_dimension_low_quality() -> None:
    rule = _REGISTRY.get("IOS4-078")
    tokens = ("воздуховод", "прямоугольный", "установлен")
    pages = {
        DocStage.PD: _page(DocStage.PD, "078-lq", *tokens),
        DocStage.RD: _page(DocStage.RD, "078-lq", *tokens),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY


def test_ios4_079_is_executable() -> None:
    rule = _REGISTRY.get("IOS4-079")
    assert rule["coverage"] == "executable"
    assert rule["extractor"]["type"] == "number"
    assert rule["comparator"]["operator"] == "delta"


def test_ios4_079_same_airflow_no_difference() -> None:
    rule = _REGISTRY.get("IOS4-079")
    tokens = ("приточная установка", "производительность", "1000", "м³/ч")
    pages = {
        DocStage.PD: _page(DocStage.PD, "079-eq", *tokens),
        DocStage.RD: _page(DocStage.RD, "079-eq", *tokens),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None


def test_ios4_079_mismatch_gives_candidate() -> None:
    rule = _REGISTRY.get("IOS4-079")
    pages = {
        DocStage.PD: _page(
            DocStage.PD, "079-cand", "приточная установка", "расход", "1000", "м³/ч"
        ),
        DocStage.RD: _page(
            DocStage.RD, "079-cand", "венткамера", "расход воздуха", "800", "м³/ч"
        ),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.disagreement_kind is DisagreementKind.VALUE_DELTA


def test_ios4_079_rd_missing() -> None:
    rule = _REGISTRY.get("IOS4-079")
    pages = {DocStage.PD: _page(DocStage.PD, "079-me", "приточная установка", "1000", "м³/ч")}
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness_no_rd()
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE


def test_ios4_079_no_airflow_unit_low_quality() -> None:
    rule = _REGISTRY.get("IOS4-079")
    tokens = ("приточная установка", "вентилятор", "тип-ВО-001")
    pages = {
        DocStage.PD: _page(DocStage.PD, "079-lq", *tokens),
        DocStage.RD: _page(DocStage.RD, "079-lq", *tokens),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY


def test_executable_count_includes_ios4() -> None:
    executable = [
        code for code in _REGISTRY.all_codes() if _REGISTRY.get(code)["coverage"] == "executable"
    ]
    assert "IOS4-078" in executable
    assert "IOS4-079" in executable
    assert len(executable) >= 28


def test_multiply_dimensions_is_opt_in() -> None:
    steps_area = ("nfc", "collapse_spaces", "decimal_comma", "multiply_dimensions")
    assert parse_number("500×300", steps_area) == 150_000.0
    assert parse_number("500 × 300", steps_area) == 150_000.0
    assert parse_number("500,5×200", steps_area) == 100_100.0
    assert parse_number("1500", ("nfc", "collapse_spaces", "decimal_comma")) == 1500.0


def test_ios4_078_area_from_spaced_tokens() -> None:
    rule = _REGISTRY.get("IOS4-078")
    pages = {
        DocStage.PD: _page(DocStage.PD, "078-sp", "сечение воздуховода", "500", "×", "300"),
        DocStage.RD: _page(DocStage.RD, "078-sp", "сечение воздуховода", "500", "×", "300"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.expected_value == 150_000.0


def _headed(
    stage: DocStage,
    file_id: str,
    code: str,
    words: tuple[str, ...],
    extra: tuple[PageToken, ...] = (),
) -> tuple[StagePage, DocumentRef]:
    document = replace(_doc(stage, file_id), file_id=file_id, document_code=code)
    return StagePage(document=document, tokens=_line(*words) + extra), document


def test_ios4_binds_ov_volume_not_the_neighbouring_section() -> None:
    """Шифр тома — марка ОВ/ОВ1, не секция матрицы ИОС4. Чужой том число не отдаёт."""

    rule = _REGISTRY.get("IOS4-078")
    pd_ov, doc_pd_ov = _headed(
        DocStage.PD,
        "pd-ov",
        "АНО/150321/1-П-ОВ",
        ("воздуховод", "сечение", "500×300", "мм"),
        (_tok("140", 0.20, 0.20), _tok("В", 0.24, 0.20)),
    )
    pd_ar, doc_pd_ar = _headed(
        DocStage.PD,
        "pd-ar",
        "АНО/150321/1-П-АР",
        ("воздуховод", "сечение", "100×100", "мм"),
    )
    rd_ov, doc_rd_ov = _headed(
        DocStage.RD,
        "rd-ov",
        "АНО/150321/1-РД-ОВ1",
        ("воздуховод", "сечение", "400×200", "мм"),
        (_tok("140", 0.20, 0.20),),
    )
    rd_kr, doc_rd_kr = _headed(
        DocStage.RD,
        "rd-kr",
        "АНО/150321/1-РД-КР",
        ("воздуховод", "сечение", "100×100", "мм"),
    )
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: (pd_ar, pd_ov),
            DocStage.RD: (rd_kr, rd_ov),
        },
        completeness=_completeness(),
        revision_pool=[doc_pd_ar, doc_pd_ov, doc_rd_kr, doc_rd_ov],
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.source_id == "pd-ov"
    assert result.finding.expected_value == 150_000.0
    assert result.finding.actual_value == 80_000.0
    assert result.evidence_group is not None
    assert {item.document.file_id for item in result.evidence_group.fragments} == {
        "pd-ov",
        "rd-ov",
    }
    rooms = [
        item
        for item in result.also
        if item.evidence_group is not None
        and any(fragment.room_id == "140" for fragment in item.evidence_group.fragments)
    ]
    assert rooms
    assert rooms[0].finding.finding_status is FindingStatus.CANDIDATE
    assert rooms[0].finding.source_id == "pd-ov"
    assert {
        fragment.document.file_id for fragment in rooms[0].evidence_group.fragments
    } == {"pd-ov", "rd-ov"}


def test_two_ov_volumes_ask_instead_of_picking_one() -> None:
    rule = _REGISTRY.get("IOS4-078")
    first, doc_first = _headed(
        DocStage.PD,
        "pd-ov1",
        "АНО/150321/1-П-ОВ1",
        ("воздуховод", "сечение", "500×300", "мм"),
    )
    second, doc_second = _headed(
        DocStage.PD,
        "pd-ov2",
        "АНО/150321/1-П-ОВ2",
        ("воздуховод", "сечение", "100×100", "мм"),
    )
    rd, doc_rd = _headed(
        DocStage.RD,
        "rd-ov",
        "АНО/150321/1-РД-ОВ1",
        ("воздуховод", "сечение", "400×200", "мм"),
    )
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={DocStage.PD: (first, second), DocStage.RD: rd},
        completeness=_completeness(),
        revision_pool=[doc_first, doc_second, doc_rd],
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert "несколько голов" in result.finding.rationale
    assert "pd-ov1" in result.finding.rationale
    assert "pd-ov2" in result.finding.rationale
    assert result.also == ()
    assert result.evidence_group is None
