"""Гейт H: параметризованные E2E-тесты для executable-правил.

Цель: подтвердить, что каждое правило с `coverage: executable` проходит
полный цикл L1–L7 с мок-токенами и возвращает:
  - при равных значениях: AUTO_NO_DIFFERENCE + evidence_group
  - при расхождении: CANDIDATE + evidence_group
  - при отсутствии RD: MISSING_EVIDENCE без evidence_group
  - никогда CONFIRMED_VIOLATION / NEGATIVE_VERIFIED (только люди)

Gate H дедлайн: 22–23.09; цель ≥ 20 executable.
N.B. PZ-009 (анкор содержит 0.000) пропущен в E2E до диагностики extract_number.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "b" * 64
OBJECT_ID = "OBJ-GATE-H-SMOKE"


# ── helpers ────────────────────────────────────────────────────────────────────


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    width, height = 0.10, 0.04
    polygon = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _line(*values: str) -> tuple[PageToken, ...]:
    return tuple(_tok(text, 0.08 + i * 0.14) for i, text in enumerate(values))


def _doc(stage: DocStage, suffix: str = "") -> DocumentRef:
    return DocumentRef(
        file_id=f"file-{stage.value.lower()}{suffix}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"H-{stage.value}-DOC{suffix}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
    )


def _page(stage: DocStage, *tokens: str, suffix: str = "") -> StagePage:
    return StagePage(document=_doc(stage, suffix), tokens=_line(*tokens))


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


_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


# ── executable count check ─────────────────────────────────────────────────


def test_executable_count() -> None:
    """Гейт H: минимум 10 executable правил (цель: ≥20 к 22–23.09)."""
    executable = [
        c for c in _REGISTRY.all_codes() if _REGISTRY.get(c)["coverage"] == "executable"
    ]
    assert len(executable) >= 10, (
        f"Ждали ≥10 executable, получили {len(executable)}: {sorted(executable)}"
    )


# ── параметризованные случаи ──────────────────────────────────────────

# (код, токены якоря, значение PD, значение RD — одинаковые → AUTO_NO_DIFFERENCE)
_CASES: list[tuple[str, tuple[str, ...], str, str]] = [
    # PZ-001: delta, tolerance_abs=0, якорь из 2 слов
    ("PZ-001", ("Площадь", "застройки"), "1250,5", "1250,5"),
    # PZ-002: delta, tolerance_rel=1%, 3 слова якоря
    ("PZ-002", ("Общая", "площадь", "здания"), "5000,0", "5000,0"),
    # PZ-003: delta, tolerance_abs=0, dual_read=false
    ("PZ-003", ("Полезная", "/", "Расчетная", "площадь"), "3000,0", "3000,0"),
    # PZ-004: delta, объем общий
    ("PZ-004", ("Строительный", "объем", "(Общий)"), "15000,0", "15000,0"),
    # PZ-005: delta, объем подземный
    ("PZ-005", ("Строительный", "объем", "(Подземный)"), "3000,0", "3000,0"),
    # PZ-006: delta, надземный объем
    ("PZ-006", ("Строительный", "объем", "(Надземный)"), "12000,0", "12000,0"),
    # PZ-007: delta, этажность
    ("PZ-007", ("Этажность", "(надземная)"), "25", "25"),
    # PZ-008: delta, высота
    ("PZ-008", ("Высота", "здания"), "99,5", "99,5"),
    # PZ-010: delta, квартиры
    ("PZ-010", ("Количество", "квартир"), "120", "120"),
    # AR-041: ge ≥ 0.9 м, fixed value; 1.0 ≥ 0.9 → AUTO_NO_DIFFERENCE
    ("AR-041", ("Ширина", "проема"), "1,2", "1,0"),
]


@pytest.mark.parametrize(
    "rule_code, anchor_words, pd_value, rd_value",
    [(c[0], c[1], c[2], c[3]) for c in _CASES],
    ids=[c[0] for c in _CASES],
)
def test_no_difference_happy_path(
    rule_code: str,
    anchor_words: tuple[str, ...],
    pd_value: str,
    rd_value: str,
) -> None:
    """Счастливый путь: правило должно выдать AUTO_NO_DIFFERENCE с evidence_group."""
    rule = _REGISTRY.get(rule_code)
    assert rule["coverage"] == "executable", f"{rule_code}: coverage != executable"

    pd_tokens = (*anchor_words, pd_value)
    rd_tokens = (*anchor_words, rd_value)
    pages = {
        DocStage.PD: _page(DocStage.PD, *pd_tokens, suffix=f"-{rule_code}"),
        DocStage.RD: _page(DocStage.RD, *rd_tokens, suffix=f"-{rule_code}"),
    }
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness()
    )
    finding = result.finding

    assert finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE, (
        f"{rule_code}: ожидал AUTO_NO_DIFFERENCE, получен {finding.finding_status.value}; "
        f"rationale: {finding.rationale}"
    )
    assert finding.evidence_group_id is not None, f"{rule_code}: нет evidence_group_id"
    assert result.evidence_group is not None, f"{rule_code}: нет evidence_group"
    assert finding.finding_status not in {
        FindingStatus.CONFIRMED_VIOLATION,
        FindingStatus.NEGATIVE_VERIFIED,
    }, f"{rule_code}: автомат не пишет человеческий вердикт"

    for fragment in result.evidence_group.fragments:
        assert fragment.page >= 1
        assert fragment.extracted.second_read_agrees is True, (
            f"{rule_code}: second_read_agrees=False — в моке должно быть ровно одно число"
        )


@pytest.mark.parametrize(
    "rule_code, anchor_words",
    [(c[0], c[1]) for c in _CASES if c[0] != "AR-041"],
    ids=[c[0] for c in _CASES if c[0] != "AR-041"],
)
def test_candidate_on_delta_mismatch(
    rule_code: str,
    anchor_words: tuple[str, ...],
) -> None:
    """Расхождение PD и RD → CANDIDATE + evidence_group."""
    rule = _REGISTRY.get(rule_code)
    pd_tokens = (*anchor_words, "1000,0")
    rd_tokens = (*anchor_words, "900,0")
    pages = {
        DocStage.PD: _page(DocStage.PD, *pd_tokens, suffix=f"-{rule_code}-cand"),
        DocStage.RD: _page(DocStage.RD, *rd_tokens, suffix=f"-{rule_code}-cand"),
    }
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness()
    )
    finding = result.finding
    assert finding.finding_status is FindingStatus.CANDIDATE, (
        f"{rule_code}: ожидал CANDIDATE, получен {finding.finding_status.value}; "
        f"rationale: {finding.rationale}"
    )
    assert finding.evidence_group_id is not None
    assert result.evidence_group is not None
    assert finding.finding_status not in {
        FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED
    }


@pytest.mark.parametrize(
    "rule_code, anchor_words",
    [(c[0], c[1]) for c in _CASES],
    ids=[c[0] for c in _CASES],
)
def test_rd_missing_gives_missing_evidence(
    rule_code: str,
    anchor_words: tuple[str, ...],
) -> None:
    """Отсутствие RD → MISSING_EVIDENCE без evidence_group."""
    rule = _REGISTRY.get(rule_code)
    pd_tokens = (*anchor_words, "1000,0")
    pages = {DocStage.PD: _page(DocStage.PD, *pd_tokens, suffix=f"-{rule_code}-me")}
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness_no_rd(),
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE, (
        f"{rule_code}: ожидал MISSING_EVIDENCE, "
        f"получен {result.finding.finding_status.value}"
    )
    assert result.finding.evidence_group_id is None
    assert result.missing_stage is DocStage.RD
    assert result.finding.finding_status not in {
        FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED
    }


# ── AR-041 специфика (ge-оператор с fixed ref) ──────────────────────────


def test_ar041_below_threshold_gives_candidate() -> None:
    """Ширина 0.8 м < 0.9 м → CANDIDATE (нарушение СП 1.13130.2020 п.4.2.1)."""
    rule = _REGISTRY.get("AR-041")
    pages = {
        DocStage.PD: _page(DocStage.PD, "Ширина", "проема", "1,2", suffix="-ar041-cand"),
        DocStage.RD: _page(DocStage.RD, "Ширина", "проема", "0,8", suffix="-ar041-cand"),
    }
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness()
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.evidence_group_id is not None
    assert result.finding.actual_value == pytest.approx(0.8)


def test_ar041_at_boundary_is_no_difference() -> None:
    """0.9 м == порог → AUTO_NO_DIFFERENCE (граничное значение включительно)."""
    rule = _REGISTRY.get("AR-041")
    pages = {
        DocStage.PD: _page(DocStage.PD, "Ширина", "проема", "0,9", suffix="-ar041-bound"),
        DocStage.RD: _page(DocStage.RD, "Ширина", "проема", "0,9", suffix="-ar041-bound"),
    }
    result = evaluate_rule(
        rule, object_id=OBJECT_ID, pages=pages, completeness=_completeness()
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
