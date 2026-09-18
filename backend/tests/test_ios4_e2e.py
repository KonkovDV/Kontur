"""Тесты E2E для IOS4-078 (сечения воздуховодов, оператор ge)
и IOS4-079 (вентиляторы ОВ, оператор ne) — Gate O, PR #23.

Критичность: GAP-IOS4 (P1/S1).
  - До PR #23 оба правила возвращали CLARIFICATION_REQUIRED вместо CANDIDATE.
  - evaluate.py отклонял extractor.type=semantic_candidate/geometry.
  - Critical recall = 0 для этих правил → кап 59/100.
  - После PR #23: type=number, executable, 29+ executable правил.
Структура тестов: повторяет паттерн test_kr055_e2e.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kontur.application.evaluate import RuleEvaluation, StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus

# ── фикстуры ────────────────────────────────────────────────────────────────────────

RULES_DIR = Path(__file__).resolve().parents[2] / "data" / "matrix" / "rules"

_POLY = ((0.1, 0.1), (0.3, 0.1), (0.3, 0.3), (0.1, 0.3))

_COMPLETENESS_BOTH: CompletenessMap = {
    DocStage.PD: Completeness.PRESENT,
    DocStage.RD: Completeness.PRESENT,
}
_COMPLETENESS_NO_RD: CompletenessMap = {
    DocStage.PD: Completeness.PRESENT,
    DocStage.RD: Completeness.MISSING,
}


def _load_rule(code: str) -> dict:
    return json.loads((RULES_DIR / f"{code}.json").read_text(encoding="utf-8"))


def _doc(file_id: str, stage: DocStage) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash="a" * 64,
        doc_stage=stage,
        document_code=f"OV-{stage.value}-001",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )


def _page(tokens_text: list[str], stage: DocStage) -> StagePage:
    tokens = tuple(
        PageToken(text=t, page=1, polygon_source=_POLY, polygon_norm=_POLY)
        for t in tokens_text
    )
    return StagePage(document=_doc(f"doc-{stage.value}-ios4", stage), tokens=tokens)


def _eval(
    rule: dict,
    pd_tokens: list[str],
    rd_tokens: list[str],
    completeness: CompletenessMap = _COMPLETENESS_BOTH,
) -> FindingStatus:
    pages = {
        DocStage.PD: _page(pd_tokens, DocStage.PD),
        DocStage.RD: _page(rd_tokens, DocStage.RD),
    }
    result = evaluate_rule(
        rule, object_id="OBJ-IOS4-TEST", pages=pages, completeness=completeness
    )
    return result.finding.finding_status


# ═══════════════════════════════════════════════════════════════════════════════
# IOS4-079 — Вентиляторы ОВ (кратность воздухообмена, м³/ч, operator ne)
# ═══════════════════════════════════════════════════════════════════════════════


class TestIOS4_079:  # noqa: N801
    """IOS4-079: подмена вентилятора на аналог с меньшей кратностью воздухообмена."""

    @classmethod
    def setup_class(cls) -> None:
        cls.rule = _load_rule("IOS4-079")

    def test_rule_is_now_executable(self) -> None:
        """Регрессия: краснеет если вернуть semantic_candidate."""
        assert self.rule["coverage"] == "executable"
        assert self.rule["extractor"]["type"] == "number"
        assert self.rule["comparator"]["operator"] == "ne"

    def test_same_airflow_pd_equals_rd_gives_no_difference(self) -> None:
        """ПД = РД = 1000 м³/ч → AUTO_NO_DIFFERENCE."""
        tokens = ["приточная установка", "производительность", "1000", "м³/ч"]
        assert _eval(self.rule, tokens, tokens) is FindingStatus.AUTO_NO_DIFFERENCE

    def test_reduced_airflow_in_rd_gives_candidate(self) -> None:
        """ПД: 1000 м³/ч, РД: 800 м³/ч — подмена → CANDIDATE."""
        pd = ["приточная установка", "расход", "1000", "м³/ч"]
        rd = ["венткамера", "расход воздуха", "800", "м³/ч"]
        assert _eval(self.rule, pd, rd) is FindingStatus.CANDIDATE

    def test_increased_airflow_in_rd_also_gives_candidate(self) -> None:
        """Аналог с большим расходом: ПД 1000, РД 1200 — несоответствие → CANDIDATE (ne)."""
        pd = ["венткамера", "кратность воздухообмена", "1000", "м³/ч"]
        rd = ["приточная установка", "поток", "1200", "м³/ч"]
        assert _eval(self.rule, pd, rd) is FindingStatus.CANDIDATE

    def test_rd_missing_gives_missing_evidence(self) -> None:
        """РД отсутствует → MISSING_EVIDENCE."""
        pd = ["приточная установка", "1000", "м³/ч"]
        pages = {DocStage.PD: _page(pd, DocStage.PD)}
        result = evaluate_rule(
            self.rule,
            object_id="OBJ-IOS4-TEST",
            pages=pages,
            completeness=_COMPLETENESS_NO_RD,
        )
        assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE

    def test_no_airflow_unit_gives_low_quality(self) -> None:
        """Нет единицы м³/ч → анкер не находит число → LOW_QUALITY."""
        tokens = ["приточная установка", "вентилятор", "тип-ВО-001"]  # нет м³/ч
        assert _eval(self.rule, tokens, tokens) is FindingStatus.LOW_QUALITY


# ═══════════════════════════════════════════════════════════════════════════════
# IOS4-078 — Сечения воздуховодов (мм, operator ge, RD >= PD)
# ═══════════════════════════════════════════════════════════════════════════════


class TestIOS4_078:  # noqa: N801
    """IOS4-078: уменьшение сечения воздуховода в РД (падение объёма воздуха, рост шума)."""

    @classmethod
    def setup_class(cls) -> None:
        cls.rule = _load_rule("IOS4-078")

    def test_rule_is_now_executable(self) -> None:
        """Регрессия: краснеет если вернуть geometry."""
        assert self.rule["coverage"] == "executable"
        assert self.rule["extractor"]["type"] == "number"
        assert self.rule["comparator"]["operator"] == "ge"

    def test_same_duct_section_gives_no_difference(self) -> None:
        """ПД = РД = 500×300 мм → AUTO_NO_DIFFERENCE (ge: 500 >= 500)."""
        tokens = ["сечение воздуховода", "500×300", "мм"]
        assert _eval(self.rule, tokens, tokens) is FindingStatus.AUTO_NO_DIFFERENCE

    def test_reduced_duct_section_gives_candidate(self) -> None:
        """ПД: 500×300, РД: 400×200 — уменьшение сечения → CANDIDATE (400 < 500)."""
        pd = ["воздуховод", "сечение", "500×300", "мм"]
        rd = ["воздуховод", "сечение", "400×200", "мм"]
        assert _eval(self.rule, pd, rd) is FindingStatus.CANDIDATE

    def test_larger_rd_section_gives_no_difference(self) -> None:
        """РД ≥ ПД: 600×400 ≥ 500×300 — не нарушение → AUTO_NO_DIFFERENCE (ge)."""
        pd = ["сечение воздуховода", "500×300"]
        rd = ["воздуховод", "600×400"]
        assert _eval(self.rule, pd, rd) is FindingStatus.AUTO_NO_DIFFERENCE

    def test_rd_missing_gives_missing_evidence(self) -> None:
        """РД отсутствует → MISSING_EVIDENCE."""
        pages = {DocStage.PD: _page(["сечение воздуховода", "500×300"], DocStage.PD)}
        result = evaluate_rule(
            self.rule,
            object_id="OBJ-IOS4-TEST",
            pages=pages,
            completeness=_COMPLETENESS_NO_RD,
        )
        assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE

    def test_no_duct_dimension_gives_low_quality(self) -> None:
        """Нет паттерна NNN× → LOW_QUALITY."""
        tokens = ["воздуховод", "прямоугольный", "установлен"]
        assert _eval(self.rule, tokens, tokens) is FindingStatus.LOW_QUALITY


# ── executable count ────────────────────────────────────────────────────────────────────


def test_executable_count_reaches_29_after_ios4() -> None:
    """После PR #23: IOS4-078 + IOS4-079 → executable ≥ 29.

    Регрессия: краснеет если оба правила вернуть coverage=extractor_missing.
    """
    count = sum(
        1
        for f in RULES_DIR.glob("*.json")
        if json.loads(f.read_text(encoding="utf-8")).get("coverage") == "executable"
    )
    assert count >= 29, (
        f"Ожидали ≥29 executable правил (IOS4-078/079 переведены), получено {count}"
    )
