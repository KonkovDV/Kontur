"""Фикстуры правил, переведённых в executable триажем семейств (issue #82 → #83).

Тесты исполняют РЕАЛЬНЫЕ правила из `data/matrix/rules/`, а не синтетические
скелеты: обещание override-а проверяется тем же движком, что и в проде.
Ни один тест не объявляет покрытие 132/132 и не закрывает Gate J.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kontur.application.evaluate import RuleEvaluation, StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_RULES = REPO_ROOT / "data" / "matrix" / "rules"

HASH = "b" * 64
OBJECT_ID = "OBJ-FAMILY-TRIAGE"


def rule(code: str) -> dict[str, object]:
    return json.loads((MATRIX_RULES / f"{code}.json").read_text(encoding="utf-8"))


def _token(text: str, index: int) -> PageToken:
    x = 0.05 + index * 0.11
    polygon = ((x, 0.40), (x + 0.09, 0.40), (x + 0.09, 0.45), (x, 0.45))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def page(stage: DocStage, *words: str) -> StagePage:
    return StagePage(
        document=DocumentRef(
            file_id=f"triage-{stage.value.lower()}",
            file_hash=HASH,
            doc_stage=stage,
            document_code="TRIAGE-FIXTURE",
            revision="1",
            approval_status=ApprovalStatus.APPROVED,
        ),
        tokens=tuple(_token(word, i) for i, word in enumerate(words)),
    )


def _completeness(
    *, rd: Completeness = Completeness.UPLOADED
) -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: rd,
        DocStage.ID: Completeness.MISSING,
    }


def run(code: str, pd: StagePage | None, rd: StagePage | None) -> RuleEvaluation:
    pages: dict[DocStage, StagePage] = {}
    if pd is not None:
        pages[DocStage.PD] = pd
    if rd is not None:
        pages[DocStage.RD] = rd
    return evaluate_rule(
        rule(code),
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness(
            rd=Completeness.UPLOADED if rd is not None else Completeness.MISSING
        ),
    )


def status(code: str, pd: StagePage | None, rd: StagePage | None) -> FindingStatus:
    return run(code, pd, rd).finding.finding_status


# ── AR-052: колористика фасада по коду RAL ──────────────────────────────────

AR052_PD = page(DocStage.PD, "Цвет", "фасада", "RAL", "7016")


def test_ar052_same_ral_code_is_auto_no_difference() -> None:
    result = run("AR-052", AR052_PD, page(DocStage.RD, "Цвет", "фасада", "RAL", "7016"))
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None
    assert len(result.evidence_group.fragments) == 2


def test_ar052_space_inside_ral_code_is_normalized() -> None:
    assert status("AR-052", AR052_PD, page(DocStage.RD, "Цвет", "фасада", "RAL7016")) is (
        FindingStatus.AUTO_NO_DIFFERENCE
    )


def test_ar052_changed_ral_code_is_candidate_not_a_verdict() -> None:
    result = run("AR-052", AR052_PD, page(DocStage.RD, "Цвет", "фасада", "RAL", "9003"))
    finding = result.finding
    assert finding.finding_status is FindingStatus.CANDIDATE
    assert finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert finding.expected_value == "RAL7016"
    assert finding.actual_value == "RAL9003"
    assert finding.evidence_group_id is not None
    assert len(finding.evidence_refs) == 2


def test_ar052_missing_rd_is_missing_evidence_not_a_violation() -> None:
    assert status("AR-052", AR052_PD, None) is FindingStatus.MISSING_EVIDENCE


def test_ar052_vendor_article_without_ral_is_low_quality() -> None:
    assert status(
        "AR-052", AR052_PD, page(DocStage.RD, "Цвет", "фасада", "Артикул", "AL-2205")
    ) is FindingStatus.LOW_QUALITY


def test_ar052_two_ral_codes_in_one_window_abstain() -> None:
    noisy = page(DocStage.PD, "Цвет", "фасада", "RAL", "7016", "RAL", "9003")
    assert status("AR-052", noisy, page(DocStage.RD, "Цвет", "фасада", "RAL", "7016")) is (
        FindingStatus.ABSTAIN
    )


# ── POS-087: технология возведения ──────────────────────────────────────────

POS087_PD = page(DocStage.PD, "Технология", "возведения", "монолитная")


def test_pos087_same_technology_is_auto_no_difference() -> None:
    assert status(
        "POS-087", POS087_PD, page(DocStage.RD, "Технология", "возведения", "монолитная")
    ) is FindingStatus.AUTO_NO_DIFFERENCE


def test_pos087_monolithic_replaced_by_precast_is_candidate() -> None:
    rd = page(DocStage.RD, "Технология", "возведения", "сборная")
    result = run("POS-087", POS087_PD, rd)
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.expected_value == "МОНОЛИТН"
    assert result.finding.actual_value == "СБОРН"


def test_pos087_word_endings_do_not_break_equality() -> None:
    assert status(
        "POS-087", POS087_PD, page(DocStage.RD, "Технология", "возведения", "монолитный")
    ) is FindingStatus.AUTO_NO_DIFFERENCE


def test_pos087_missing_rd_is_missing_evidence() -> None:
    assert status("POS-087", POS087_PD, None) is FindingStatus.MISSING_EVIDENCE


def test_pos087_technology_outside_closed_list_is_low_quality() -> None:
    assert status(
        "POS-087", POS087_PD, page(DocStage.RD, "Технология", "возведения", "кирпичная")
    ) is FindingStatus.LOW_QUALITY


def test_pos087_two_technologies_in_one_window_abstain() -> None:
    noisy = page(DocStage.PD, "Технология", "возведения", "монолитная", "и", "сборная")
    assert status(
        "POS-087", noisy, page(DocStage.RD, "Технология", "возведения", "монолитная")
    ) is FindingStatus.ABSTAIN


# ── POD-091: метод демонтажа ────────────────────────────────────────────────

POD091_PD = page(DocStage.PD, "Метод", "демонтажа", "алмазная", "резка")


def test_pod091_same_method_is_auto_no_difference() -> None:
    assert status(
        "POD-091", POD091_PD, page(DocStage.RD, "Метод", "демонтажа", "алмазная", "резка")
    ) is FindingStatus.AUTO_NO_DIFFERENCE


def test_pod091_diamond_cutting_replaced_by_collapse_is_candidate() -> None:
    rd = page(DocStage.RD, "Метод", "демонтажа", "обрушение", "экскаватором")
    result = run("POD-091", POD091_PD, rd)
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.expected_value == "АЛМАЗН"
    assert result.finding.actual_value == "ОБРУШЕНИ"


def test_pod091_missing_rd_is_missing_evidence() -> None:
    assert status("POD-091", POD091_PD, None) is FindingStatus.MISSING_EVIDENCE


def test_pod091_method_outside_closed_list_is_low_quality() -> None:
    assert status(
        "POD-091", POD091_PD, page(DocStage.RD, "Метод", "демонтажа", "взрывной")
    ) is FindingStatus.LOW_QUALITY


def test_pod091_two_methods_in_one_window_abstain() -> None:
    noisy = page(DocStage.PD, "Метод", "демонтажа", "алмазная", "резка", "и", "обрушение")
    assert status(
        "POD-091", noisy, page(DocStage.RD, "Метод", "демонтажа", "алмазная", "резка")
    ) is FindingStatus.ABSTAIN


# ── ZU-130: тип осветительного оборудования ─────────────────────────────────

ZU130_PD = page(DocStage.PD, "Тип", "светильника", "светодиодный")


def test_zu130_same_luminaire_type_is_auto_no_difference() -> None:
    assert status(
        "ZU-130", ZU130_PD, page(DocStage.RD, "Тип", "светильника", "светодиодный")
    ) is FindingStatus.AUTO_NO_DIFFERENCE


def test_zu130_led_replaced_by_incandescent_is_candidate() -> None:
    result = run("ZU-130", ZU130_PD, page(DocStage.RD, "Тип", "светильника", "накаливания"))
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.expected_value == "СВЕТОДИОДН"
    assert result.finding.actual_value == "НАКАЛИВАНИ"


def test_zu130_missing_rd_is_missing_evidence() -> None:
    assert status("ZU-130", ZU130_PD, None) is FindingStatus.MISSING_EVIDENCE


def test_zu130_latin_led_marking_is_low_quality_not_silent_pass() -> None:
    """Задокументированное ограничение: латинская маркировка не распознаётся."""

    result = run("ZU-130", ZU130_PD, page(DocStage.RD, "Тип", "светильника", "LED"))
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert result.finding.finding_status is not FindingStatus.AUTO_NO_DIFFERENCE


def test_zu130_two_luminaire_types_in_one_window_abstain() -> None:
    noisy = page(DocStage.PD, "Тип", "светильника", "светодиодный", "или", "люминесцентный")
    assert status(
        "ZU-130", noisy, page(DocStage.RD, "Тип", "светильника", "светодиодный")
    ) is FindingStatus.ABSTAIN


# ── POD-095: presence остаётся advisory ─────────────────────────────────────

POD095_PD = page(DocStage.PD, "Пылеподавление", "гидроорошение")


def test_pod095_declared_on_both_stages_is_auto_no_difference() -> None:
    assert status(
        "POD-095", POD095_PD, page(DocStage.RD, "Пылеподавление", "гидроорошение")
    ) is FindingStatus.AUTO_NO_DIFFERENCE


def test_pod095_absent_in_rd_is_low_quality_never_candidate() -> None:
    result = run("POD-095", POD095_PD, page(DocStage.RD, "Уборка", "территории"))
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert result.finding.finding_status is not FindingStatus.CANDIDATE
    assert result.evidence_group is None


def test_pod095_missing_rd_is_missing_evidence() -> None:
    assert status("POD-095", POD095_PD, None) is FindingStatus.MISSING_EVIDENCE


def test_pod095_stays_advisory_because_presence_cannot_accuse() -> None:
    payload = rule("POD-095")
    assert payload["coverage"] == "advisory"
    comparator = payload["comparator"]
    assert isinstance(comparator, dict)
    assert comparator["operator"] == "present"


# ── OOS-098..101: источник вне пакета ───────────────────────────────────────


@pytest.mark.parametrize("code", ["OOS-098", "OOS-099", "OOS-100", "OOS-101"])
def test_registry_rules_fail_closed_without_a_regex(code: str) -> None:
    payload = rule(code)
    assert payload["coverage"] == "source_missing"
    extractor = payload["extractor"]
    assert isinstance(extractor, dict)
    assert extractor["regex"] is None
    assert status(
        code,
        page(DocStage.PD, "Статус", "открыт"),
        page(DocStage.RD, "Статус", "закрыт"),
    ) is FindingStatus.LOW_QUALITY


# ── гейт покрытия в _finding_from_comparison ────────────────────────────────


def _synthetic(coverage: str) -> dict[str, object]:
    return {
        "code": "FIXTURE-COVERAGE-GATE",
        "matrix_version": "fixture-1",
        "unit": "—",
        "coverage": coverage,
        "extractor": {
            "type": "exact_field",
            "regex": "(наружу|внутрь)",
            "anchors": ["Направление открывания"],
            "normalization": ["nfc", "collapse_spaces", "upper"],
            "dual_read_required": False,
        },
        "comparator": {"operator": "eq"},
        "failure_mapping": {
            "source_absent": "MISSING_EVIDENCE",
            "not_comparable": "NOT_COMPARABLE",
            "revision_conflict": "CLARIFICATION_REQUIRED",
            "low_quality": "LOW_QUALITY",
            "reads_disagree": "ABSTAIN",
        },
        "review_priority": "HIGH",
    }


def _gate(coverage: str) -> RuleEvaluation:
    return evaluate_rule(
        _synthetic(coverage),
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: page(DocStage.PD, "Направление", "открывания", "наружу"),
            DocStage.RD: page(DocStage.RD, "Направление", "открывания", "внутрь"),
        },
        completeness=_completeness(),
    )


def test_executable_coverage_still_publishes_a_candidate() -> None:
    assert _gate("executable").finding.finding_status is FindingStatus.CANDIDATE


@pytest.mark.parametrize("coverage", ["advisory", "source_missing", "not_applicable"])
def test_incomplete_coverage_downgrades_candidate_to_low_quality(coverage: str) -> None:
    """Честное покрытие сильнее сработавшего экстрактора: обвинения не публикуем."""

    result = _gate(coverage)
    finding = result.finding
    assert finding.finding_status is FindingStatus.LOW_QUALITY
    assert finding.finding_status is not FindingStatus.CANDIDATE
    assert finding.expected_value == "НАРУЖУ"
    assert finding.actual_value == "ВНУТРЬ"
    assert finding.evidence_group_id is not None
    assert len(finding.evidence_refs) == 2
    assert f"coverage={coverage}" in str(finding.rationale)
    assert result.evidence_group is not None
