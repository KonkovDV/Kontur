"""Вертикальные E2E-тесты enum/number-правил:
  PZ-013 (вместимость, number+ge)
  PZ-015 (категория надежности, enum [1,2,3])
  PZ-021 (класс энергоэффективности, enum G→A++)
  PZ-022 (степень огнестойкости, enum V→I)
  PZ-023 (класс пожарной опасности, enum C3→C0)

Цель: подтвердить L1-L7 цикл и соответствие ADR-0001
(машина не пишет CONFIRMED_VIOLATION/NEGATIVE_VERIFIED).
"""

from __future__ import annotations

from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "c" * 64
OBJECT_ID = "OBJ-PZ-ENUM-SMOKE"

_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    p = ((x, y), (x + 0.10, y), (x + 0.10, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=p, polygon_norm=p)


def _line(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(w, 0.05 + i * 0.13) for i, w in enumerate(words))


def _doc(stage: DocStage, suffix: str) -> DocumentRef:
    return DocumentRef(
        file_id=f"pz-enum-{stage.value.lower()}-{suffix}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"PZ-ENUM-{stage.value}-{suffix}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
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


# ── PZ-013: Технологическая мощность / Вместимость (number + ge) ──────────


def test_pz013_is_executable() -> None:
    r = _REGISTRY.get("PZ-013")
    assert r["coverage"] == "executable"
    assert r["extractor"]["type"] == "number"
    assert r["comparator"]["operator"] == "ge"


def test_pz013_equal_capacity_no_difference() -> None:
    """PZ-013: 500 == 500 → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-013")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz013", "Технологическая", "мощность", "/", "Вместимость", "500"),
        DocStage.RD: _page(DocStage.RD, "pz013", "Технологическая", "мощность", "/", "Вместимость", "500"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.evidence_group_id is not None


def test_pz013_higher_capacity_no_difference() -> None:
    """PZ-013: 600 > 500 (увеличение) → AUTO_NO_DIFFERENCE (не нарушение)."""
    rule = _REGISTRY.get("PZ-013")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz013hi", "Технологическая", "мощность", "/", "Вместимость", "500"),
        DocStage.RD: _page(DocStage.RD, "pz013hi", "Технологическая", "мощность", "/", "Вместимость", "600"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_pz013_lower_capacity_gives_candidate() -> None:
    """PZ-013: 450 < 500 (снижение) → CANDIDATE."""
    rule = _REGISTRY.get("PZ-013")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz013lo", "Технологическая", "мощность", "/", "Вместимость", "500"),
        DocStage.RD: _page(DocStage.RD, "pz013lo", "Технологическая", "мощность", "/", "Вместимость", "450"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


# ── PZ-015: Категория надежности электроснабжения (enum [3,2,1]) ─────────


def test_pz015_is_executable() -> None:
    r = _REGISTRY.get("PZ-015")
    assert r["coverage"] == "executable"
    assert r["extractor"]["type"] == "enum"
    assert r["comparator"]["operator"] == "class_not_lower"


def test_pz015_same_category_no_difference() -> None:
    """PZ-015: категория 1 = 1 → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-015")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz015", "Категория", "надежности", "электроснабжения", "1"),
        DocStage.RD: _page(DocStage.RD, "pz015", "Категория", "надежности", "электроснабжения", "1"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None
    assert len(result.evidence_group.fragments) == 2


def test_pz015_category_lowered_gives_candidate() -> None:
    """PZ-015: PD=кат.1, RD=кат.2 (снижение надежности) → CANDIDATE."""
    rule = _REGISTRY.get("PZ-015")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz015lo", "Категория", "надежности", "электроснабжения", "1"),
        DocStage.RD: _page(DocStage.RD, "pz015lo", "Категория", "надежности", "электроснабжения", "2"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_pz015_category_improved_no_difference() -> None:
    """PZ-015: PD=кат.2, RD=кат.1 (улучшение надежности) → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-015")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz015hi", "Категория", "надежности", "электроснабжения", "2"),
        DocStage.RD: _page(DocStage.RD, "pz015hi", "Категория", "надежности", "электроснабжения", "1"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


# ── PZ-021: Класс энергоэффективности (enum G→A++) ──────────────────


def test_pz021_is_executable() -> None:
    r = _REGISTRY.get("PZ-021")
    assert r["coverage"] == "executable"
    assert r["extractor"]["type"] == "enum"
    assert r["comparator"]["value"] == ["G", "F", "E", "D", "C", "B", "A", "A+", "A++"]


def test_pz021_same_class_no_difference() -> None:
    """PZ-021: A = A → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-021")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz021eq", "Класс", "энергетической", "эффективности", "A"),
        DocStage.RD: _page(DocStage.RD, "pz021eq", "Класс", "энергетической", "эффективности", "A"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None


def test_pz021_lower_class_gives_candidate() -> None:
    """PZ-021: PD=A, RD=B (A+→B = снижение) → CANDIDATE."""
    rule = _REGISTRY.get("PZ-021")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz021lo", "Класс", "энергетической", "эффективности", "A"),
        DocStage.RD: _page(DocStage.RD, "pz021lo", "Класс", "энергетической", "эффективности", "B"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_pz021_higher_class_no_difference() -> None:
    """PZ-021: PD=B, RD=A (улучшение) → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-021")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz021hi", "Класс", "энергетической", "эффективности", "B"),
        DocStage.RD: _page(DocStage.RD, "pz021hi", "Класс", "энергетической", "эффективности", "A"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


# ── PZ-022: Степень огнестойкости (ФЗ-123, V→I) ──────────────────────


def test_pz022_is_executable() -> None:
    r = _REGISTRY.get("PZ-022")
    assert r["coverage"] == "executable"
    assert r["comparator"]["value"] == ["V", "IV", "III", "II", "I"]


def test_pz022_same_degree_no_difference() -> None:
    """PZ-022: II = II → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-022")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz022eq", "Степень", "огнестойкости", "здания", "II"),
        DocStage.RD: _page(DocStage.RD, "pz022eq", "Степень", "огнестойкости", "здания", "II"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None


def test_pz022_lower_degree_gives_candidate() -> None:
    """PZ-022: PD=I, RD=II (снижение огнестойкости, ФЗ-123) → CANDIDATE."""
    rule = _REGISTRY.get("PZ-022")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz022lo", "Степень", "огнестойкости", "здания", "I"),
        DocStage.RD: _page(DocStage.RD, "pz022lo", "Степень", "огнестойкости", "здания", "II"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_pz022_higher_degree_no_difference() -> None:
    """PZ-022: PD=II, RD=I (улучшение) → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-022")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz022hi", "Степень", "огнестойкости", "здания", "II"),
        DocStage.RD: _page(DocStage.RD, "pz022hi", "Степень", "огнестойкости", "здания", "I"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


# ── PZ-023: Класс пожарной опасности (ФЗ-123, C3→C0) ─────────────────


def test_pz023_is_executable() -> None:
    r = _REGISTRY.get("PZ-023")
    assert r["coverage"] == "executable"
    assert r["comparator"]["value"] == ["C3", "C2", "C1", "C0"]


def test_pz023_same_class_no_difference() -> None:
    """PZ-023: C0 = C0 → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-023")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz023eq", "Класс", "конструктивной", "пожарной", "опасности", "C0"),
        DocStage.RD: _page(DocStage.RD, "pz023eq", "Класс", "конструктивной", "пожарной", "опасности", "C0"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None


def test_pz023_lower_class_gives_candidate() -> None:
    """PZ-023: PD=C0, RD=C1 (снижение пож. безопасности, ФЗ-123) → CANDIDATE."""
    rule = _REGISTRY.get("PZ-023")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz023lo", "Класс", "конструктивной", "пожарной", "опасности", "C0"),
        DocStage.RD: _page(DocStage.RD, "pz023lo", "Класс", "конструктивной", "пожарной", "опасности", "C1"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_pz023_higher_class_no_difference() -> None:
    """PZ-023: PD=C1, RD=C0 (улучшение) → AUTO_NO_DIFFERENCE."""
    rule = _REGISTRY.get("PZ-023")
    pages = {
        DocStage.PD: _page(DocStage.PD, "pz023hi", "Класс", "конструктивной", "пожарной", "опасности", "C1"),
        DocStage.RD: _page(DocStage.RD, "pz023hi", "Класс", "конструктивной", "пожарной", "опасности", "C0"),
    }
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness())
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


# ── общие: отсутствие РД → MISSING_EVIDENCE (для всех пяти) ─────────────


def _check_rd_missing(code: str, *anchor_words: str) -> None:
    rule = _REGISTRY.get(code)
    pages = {DocStage.PD: _page(DocStage.PD, f"{code}-me", *anchor_words)}
    result = evaluate_rule(rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness_no_rd())
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.missing_stage is DocStage.RD
    assert result.finding.evidence_group_id is None


def test_pz013_rd_missing() -> None:
    _check_rd_missing("PZ-013", "Технологическая", "мощность", "/", "Вместимость", "500")


def test_pz015_rd_missing() -> None:
    _check_rd_missing("PZ-015", "Категория", "надежности", "электроснабжения", "1")


def test_pz021_rd_missing() -> None:
    _check_rd_missing("PZ-021", "Класс", "энергетической", "эффективности", "A")


def test_pz022_rd_missing() -> None:
    _check_rd_missing("PZ-022", "Степень", "огнестойкости", "здания", "II")


def test_pz023_rd_missing() -> None:
    _check_rd_missing("PZ-023", "Класс", "конструктивной", "пожарной", "опасности", "C0")


# ── проверка счётчика executable после всех правил ──────────────────────────


def test_all_five_rules_are_executable() -> None:
    """Все 5 правил должны быть executable."""
    for code in ("PZ-013", "PZ-015", "PZ-021", "PZ-022", "PZ-023"):
        r = _REGISTRY.get(code)
        assert r["coverage"] == "executable", f"{code}: coverage={r['coverage']}"
        assert r["extractor"]["type"] in ("number", "enum"), f"{code}: неверный тип экстрактора"
        c_op = r["comparator"]["operator"]
        assert c_op in ("ge", "class_not_lower"), f"{code}: оператор {c_op}"


def test_executable_count_reaches_27() -> None:
    """После PR #11 + PR #12 ждём не менее 26 executable правил."""
    executable = [
        c for c in _REGISTRY.all_codes() if _REGISTRY.get(c)["coverage"] == "executable"
    ]
    assert len(executable) >= 26, (
        f"Ждали ≥26 executable, получено {len(executable)}: {sorted(executable)}"
    )
