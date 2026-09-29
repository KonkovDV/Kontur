"""E2E-тесты пяти правил-«лестниц», переведённых в executable:
  KR-056  (марка стали С235→С590)
  KR-057  (класс арматуры А240→А1000)
  PPM-103 (предел огнестойкости EI 15→EI 180)
  PPM-107 (класс пожарной опасности КМ5→КМ0)
  ZU-124  (класс энергоэффективности G→A++)

Проверяем семантику «не ниже»: равный класс и улучшение — не отклонение,
понижение — CANDIDATE. Автомат не пишет CONFIRMED_VIOLATION (ADR-0001).
Отдельно закрываем кириллические омоглифы в марках стали и арматуры.
"""

from __future__ import annotations

from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "d" * 64
OBJECT_ID = "OBJ-CLASS-LADDER-SMOKE"

_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    p = ((x, y), (x + 0.08, y), (x + 0.08, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=p, polygon_norm=p)


def _line(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(w, 0.04 + i * 0.09) for i, w in enumerate(words))


def _doc(stage: DocStage, suffix: str) -> DocumentRef:
    return DocumentRef(
        file_id=f"ladder-{stage.value.lower()}-{suffix}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"LADDER-{stage.value}-{suffix}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="КР",
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


def _run(
    code: str,
    suffix: str,
    anchor: tuple[str, ...],
    pd_value: str,
    rd_value: str | None,
) -> FindingStatus:
    rule = _REGISTRY.get(code)
    pages = {DocStage.PD: _page(DocStage.PD, suffix, *anchor, pd_value)}
    completeness = _completeness_no_rd()
    if rd_value is not None:
        pages[DocStage.RD] = _page(DocStage.RD, suffix, *anchor, rd_value)
        completeness = _completeness()
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=completeness
    )
    return result.finding.finding_status


# Якорь для каждого правила, разбитый на токены так, как он лежит в документе.
ANCHORS: dict[str, tuple[str, ...]] = {
    "KR-056": ("Марка", "стали"),
    "KR-057": ("Класс", "арматуры"),
    "PPM-103": ("Предел", "огнестойкости"),
    "PPM-107": ("Класс", "пожарной", "опасности"),
    "ZU-124": ("Класс", "энергетической", "эффективности"),
}

# code → (одинаковый, лучший в РД, худший в РД)
TRIPLES: dict[str, tuple[str, str, str]] = {
    "KR-056": ("С345", "С390", "С245"),
    "KR-057": ("А500", "А600", "А400"),
    "PPM-103": ("EI 60", "EI 90", "EI 30"),
    "PPM-107": ("КМ1", "КМ0", "КМ3"),
    "ZU-124": ("B", "A", "D"),
}


def test_all_five_rules_are_executable() -> None:
    for code in TRIPLES:
        rule = _REGISTRY.get(code)
        assert rule["coverage"] == "executable", code
        assert rule["extractor"]["type"] == "enum", code
        assert rule["comparator"]["operator"] == "class_not_lower", code


def test_same_class_gives_no_difference() -> None:
    for code, (same, _better, _worse) in TRIPLES.items():
        status = _run(code, f"{code}-same", ANCHORS[code], same, same)
        assert status is FindingStatus.AUTO_NO_DIFFERENCE, (code, status)


def test_better_class_in_rd_is_not_a_violation() -> None:
    for code, (same, better, _worse) in TRIPLES.items():
        status = _run(code, f"{code}-better", ANCHORS[code], same, better)
        assert status is FindingStatus.AUTO_NO_DIFFERENCE, (code, status)


def test_lower_class_in_rd_gives_candidate() -> None:
    for code, (same, _better, worse) in TRIPLES.items():
        status = _run(code, f"{code}-worse", ANCHORS[code], same, worse)
        assert status is FindingStatus.CANDIDATE, (code, status)
        assert status is not FindingStatus.CONFIRMED_VIOLATION


def test_missing_rd_gives_missing_evidence() -> None:
    for code, (same, _better, _worse) in TRIPLES.items():
        status = _run(code, f"{code}-nord", ANCHORS[code], same, None)
        assert status is FindingStatus.MISSING_EVIDENCE, (code, status)


def test_latin_steel_grade_in_rd_matches_cyrillic_in_pd() -> None:
    """KR-056: «С345» (кириллица) в ПД и «C345» (латиница) в РД — один класс."""
    status = _run("KR-056", "kr056-homo", ANCHORS["KR-056"], "С345", "C345")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_latin_rebar_class_in_rd_matches_cyrillic_in_pd() -> None:
    """KR-057: «А500» против «A500» — омоглиф, не отклонение."""
    status = _run("KR-057", "kr057-homo", ANCHORS["KR-057"], "А500", "A500")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_latin_fire_hazard_class_matches_cyrillic() -> None:
    """PPM-107: «КМ1» против «KM1»."""
    status = _run("PPM-107", "ppm107-homo", ANCHORS["PPM-107"], "КМ1", "KM1")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE


def test_value_outside_the_ladder_is_low_quality() -> None:
    """KR-056: «С300» нет в лестнице — регулярка не совпадает, это LOW_QUALITY."""
    status = _run("KR-056", "kr056-out", ANCHORS["KR-056"], "С345", "С300")
    assert status is FindingStatus.LOW_QUALITY


def test_steel_grade_with_index_is_read_as_base_grade() -> None:
    """KR-057: «А500С» — та же лестница, индекс свариваемости не меняет класс."""
    status = _run("KR-057", "kr057-idx", ANCHORS["KR-057"], "А500", "А500С")
    assert status is FindingStatus.AUTO_NO_DIFFERENCE
