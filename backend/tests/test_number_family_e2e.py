"""E2E-тесты шести числовых правил, переведённых в executable:
  ZU-125  (толщина утеплителя наружных стен, мм)
  ZU-127  (приведённое сопротивление теплопередаче окон, м²·°С/Вт)
  ZU-128  (толщина утеплителя покрытия, мм)
  ZU-131  (удельный годовой расход тепловой энергии, кВт·ч/м²)
  SM-132  (итог сводного сметного расчёта, тыс. руб.)
  PPM-114 (расход воды на наружное пожаротушение, л/с)

Проверяем L1–L7: совпадение даёт AUTO_NO_DIFFERENCE, расхождение за допуском —
CANDIDATE, отсутствие обязательной стадии — MISSING_EVIDENCE, нечитаемое
значение — LOW_QUALITY. Автомат не пишет CONFIRMED_VIOLATION (ADR-0001).
"""

from __future__ import annotations

from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "e" * 64
OBJECT_ID = "OBJ-NUMBER-FAMILY-SMOKE"

_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")

PROMOTED = ("ZU-125", "ZU-127", "ZU-128", "ZU-131", "SM-132", "PPM-114")

# code → (якорь токенами, значение в ПД, значение в РД за допуском)
CASES: dict[str, tuple[tuple[str, ...], str, str]] = {
    "ZU-125": (("Толщина", "утеплителя", "наружных", "стен"), "200", "150"),
    "ZU-127": (("Приведенное", "сопротивление", "теплопередаче"), "0,62", "0,45"),
    "ZU-128": (("Толщина", "утеплителя", "покрытия"), "250", "180"),
    "ZU-131": (
        ("Удельный", "расход", "тепловой", "энергии", "на", "отопление"),
        "72,4",
        "95,1",
    ),
    "SM-132": (("Всего", "по", "сводному", "сметному", "расчету"), "1250000", "1500000"),
    "PPM-114": (
        ("Расход", "воды", "на", "наружное", "пожаротушение"),
        "15",
        "10",
    ),
}


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    p = ((x, y), (x + 0.05, y), (x + 0.05, y + 0.03), (x, y + 0.03))
    return PageToken(text=text, page=1, polygon_source=p, polygon_norm=p)


def _line(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(w, 0.02 + i * 0.06) for i, w in enumerate(words))


def _doc(stage: DocStage, suffix: str) -> DocumentRef:
    return DocumentRef(
        file_id=f"numfam-{stage.value.lower()}-{suffix}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"NUMFAM-{stage.value}-{suffix}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
    )


def _page(stage: DocStage, suffix: str, *words: str) -> StagePage:
    return StagePage(document=_doc(stage, suffix), tokens=_line(*words))


def _completeness(rd_uploaded: bool = True) -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED if rd_uploaded else Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _run(code: str, suffix: str, pd_value: str, rd_value: str | None) -> FindingStatus:
    rule = _REGISTRY.get(code)
    anchor = CASES[code][0]
    pages = {DocStage.PD: _page(DocStage.PD, suffix, *anchor, pd_value)}
    if rd_value is not None:
        pages[DocStage.RD] = _page(DocStage.RD, suffix, *anchor, rd_value)
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness(rd_value is not None),
    )
    return result.finding.finding_status


def test_all_six_rules_are_executable_numbers() -> None:
    for code in PROMOTED:
        rule = _REGISTRY.get(code)
        assert rule["coverage"] == "executable", code
        assert rule["extractor"]["type"] == "number", code
        assert rule["extractor"]["dual_read_required"] is True, code
        assert "decimal_comma" in rule["extractor"]["normalization"], code
        assert "strip_unit" in rule["extractor"]["normalization"], code
        assert len(rule["extractor"]["anchors"]) >= 3, code


def test_operators_and_tolerances_were_not_touched() -> None:
    """Триаж менял экстрактор, а не смысл сравнения."""
    assert _REGISTRY.get("SM-132")["comparator"]["tolerance_rel"] == 0.05
    for code in ("ZU-125", "ZU-127", "ZU-128", "ZU-131", "PPM-114"):
        comparator = _REGISTRY.get(code)["comparator"]
        assert comparator["operator"] == "delta", code
        assert comparator["tolerance_abs"] == 0.0, code


def test_equal_value_gives_no_difference() -> None:
    for code, (_anchor, value, _other) in CASES.items():
        status = _run(code, f"{code}-eq", value, value)
        assert status is FindingStatus.AUTO_NO_DIFFERENCE, (code, status)


def test_value_changed_beyond_tolerance_gives_candidate() -> None:
    for code, (_anchor, value, other) in CASES.items():
        status = _run(code, f"{code}-diff", value, other)
        assert status is FindingStatus.CANDIDATE, (code, status)
        assert status is not FindingStatus.CONFIRMED_VIOLATION


def test_required_stage_absent_gives_missing_evidence() -> None:
    for code, (_anchor, value, _other) in CASES.items():
        status = _run(code, f"{code}-nord", value, None)
        assert status is FindingStatus.MISSING_EVIDENCE, (code, status)


def test_unreadable_value_gives_low_quality() -> None:
    for code, (_anchor, value, _other) in CASES.items():
        status = _run(code, f"{code}-low", value, "н/д")
        assert status is FindingStatus.LOW_QUALITY, (code, status)


def test_decimal_comma_is_parsed_as_fraction() -> None:
    """ZU-131: «72,4» и «72.4» — одно и то же число, а не разные значения."""
    status = _run("ZU-131", "zu131-comma", "72,4", "72.4")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_thousands_separator_in_estimate_total_is_parsed() -> None:
    """SM-132: «1 250 000» с неразрывными пробелами читается как одно число."""
    status = _run("SM-132", "sm132-sep", "1\u00a0250\u00a0000", "1250000")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_estimate_total_inside_relative_tolerance_is_no_difference() -> None:
    """SM-132: допуск 5 % — уточнение сметы в РД не должно шуметь."""
    status = _run("SM-132", "sm132-tol", "1000000", "1030000")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE
