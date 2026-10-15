"""Разбор числа и марка тома по приёму AeroBIM, своим кодом.

«1.254» не угадывается. Площадь, мощность, давление, расход и доля
переводятся только внутри своей размерности. ВК — это ИОС2.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kontur.application.evaluate import StagePage, bind_stage_page, evaluate_rule
from kontur.application.extractors.number import PageToken, extract_number
from kontur.application.normalize import (
    canonical_measure_unit,
    measure_dimensions_conflict,
    parse_number,
    scale_measure_to_target,
)
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
_STEPS = ("nfc", "collapse_spaces", "decimal_comma")
HASH = "e" * 64


def test_rightmost_separator_is_the_decimal() -> None:
    assert parse_number("1,254.30", _STEPS) == pytest.approx(1254.30)
    assert parse_number("1.254,30", _STEPS) == pytest.approx(1254.30)
    assert parse_number("1,254", _STEPS) == pytest.approx(1.254)
    assert parse_number("1.254.300", _STEPS) == pytest.approx(1_254_300.0)
    assert parse_number("10.005", _STEPS) == pytest.approx(10.005)
    assert parse_number("0.500", _STEPS) == pytest.approx(0.5)


def test_one_digit_and_three_after_a_dot_is_not_guessed() -> None:
    with pytest.raises(ValueError, match="неоднозначно"):
        parse_number("1.254", _STEPS)


def test_power_pressure_flow_and_ratio_share_a_dimension() -> None:
    assert scale_measure_to_target(1.2, source_unit="МВт", target_unit="кВт") == pytest.approx(
        1200.0
    )
    assert scale_measure_to_target(0.5, source_unit="МПа", target_unit="Па") == pytest.approx(
        500_000.0
    )
    assert scale_measure_to_target(1.0, source_unit="л/с", target_unit="м³/ч") == pytest.approx(3.6)
    assert scale_measure_to_target(250.0, source_unit="‰", target_unit="%") == pytest.approx(25.0)
    assert canonical_measure_unit("мВт") is None
    assert scale_measure_to_target(100.0, source_unit="м³/ч", target_unit="м³") == pytest.approx(
        100.0
    )
    assert measure_dimensions_conflict("м³/ч", "м³") is True


def test_flow_is_not_read_as_volume() -> None:
    rule = FileRuleRegistry(REPO / "data" / "matrix").get("PZ-005")
    volume = _line("Строительный", "объем", "(Подземный)", "100", "м³")
    flow = _line("Строительный", "объем", "(Подземный)", "100", "м³/ч")
    hit = extract_number(volume, rule)
    assert hit is not None
    assert hit.extraction.normalized_value == pytest.approx(100.0)
    assert extract_number(flow, rule) is None


def test_megawatt_and_kilowatt_are_one_load() -> None:
    status = _compare(
        "PZ-014",
        ("Расчетная", "электрическая", "мощность", "1,2", "МВт"),
        ("Расчетная", "электрическая", "мощность", "1200", "кВт"),
    )
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_liters_per_second_match_cubic_meters_per_hour() -> None:
    status = _compare(
        "PPM-114",
        ("Расход", "воды", "на", "наружное", "пожаротушение", "3,6", "м³/ч"),
        ("Расход", "воды", "на", "наружное", "пожаротушение", "1", "л/с"),
    )
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_thousand_square_meters_match_the_building_area() -> None:
    """«12,5 тыс. м²» и «12500 м²» — одна общая площадь. Единица может стоять перед числом."""

    status = _compare(
        "PZ-002",
        ("Общая", "площадь", "здания", "12,5", "тыс.", "м²"),
        ("Общая", "площадь", "здания", "м²", "12500"),
    )
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_thousand_cubic_meters_match_the_building_volume() -> None:
    status = _compare(
        "PZ-005",
        ("Строительный", "объем", "(Подземный)", "1,2", "тыс.", "м³"),
        ("Строительный", "объем", "(Подземный)", "1200", "м³"),
    )
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_per_mille_matches_percent() -> None:
    status = _compare(
        "PZ-019",
        ("Коэффициент", "застройки", "(КЗ)", "250", "‰"),
        ("Коэффициент", "застройки", "(КЗ)", "25", "%"),
    )
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def _compare(code: str, pd_words: tuple[str, ...], rd_words: tuple[str, ...]) -> FindingStatus:
    rule = FileRuleRegistry(REPO / "data" / "matrix").get(code)
    result = evaluate_rule(
        rule,
        object_id="OBJ-AEROBIM-UNITS",
        pages={
            DocStage.PD: StagePage(document=_stage_doc(DocStage.PD), tokens=_line(*pd_words)),
            DocStage.RD: StagePage(document=_stage_doc(DocStage.RD), tokens=_line(*rd_words)),
        },
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.UPLOADED,
            DocStage.ID: Completeness.MISSING,
        },
    )
    return result.finding.finding_status


def _line(*words: str) -> tuple[PageToken, ...]:
    tokens = []
    for index, word in enumerate(words):
        x = 0.04 + index * 0.08
        polygon = ((x, 0.40), (x + 0.07, 0.40), (x + 0.07, 0.44), (x, 0.44))
        tokens.append(PageToken(text=word, page=1, polygon_source=polygon, polygon_norm=polygon))
    return tuple(tokens)


def _stage_doc(stage: DocStage) -> DocumentRef:
    return DocumentRef(
        file_id=f"unit-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"UNIT-{stage.value}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="1",
    )


def test_area_scales_inside_one_dimension_only() -> None:
    assert scale_measure_to_target(5000.0, source_unit="см²", target_unit="м²") == pytest.approx(
        0.5
    )
    assert scale_measure_to_target(
        150_000.0, source_unit="мм", target_unit="мм²"
    ) == pytest.approx(150_000.0)
    assert scale_measure_to_target(1.0, source_unit="м³", target_unit="см³") == pytest.approx(
        1_000_000.0
    )


def test_vk_volume_binds_to_ios2_and_architecture_does_not() -> None:
    rule = FileRuleRegistry(REPO / "data" / "matrix").get("IOS2-071")
    water = StagePage(
        document=_doc("pd-vk", discipline="ВК"),
        tokens=(),
    )
    arch = StagePage(
        document=_doc("pd-ar", discipline="архитектура"),
        tokens=(),
    )
    bound = bind_stage_page(rule, DocStage.PD, (arch, water))
    assert isinstance(bound, StagePage)
    assert bound.document.file_id == "pd-vk"


def _doc(file_id: str, *, discipline: str) -> DocumentRef:
    return replace(
        DocumentRef(
            file_id=file_id,
            file_hash=HASH,
            doc_stage=DocStage.PD,
            document_code="",
            revision="1",
            approval_status=ApprovalStatus.APPROVED,
            sheet="1",
        ),
        discipline=discipline,
    )
