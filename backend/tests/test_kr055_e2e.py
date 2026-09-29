"""Вертикальный слайс KR-055: enum-экстрактор + class_not_lower.

Гейт H+: KR-055 становится executable через text.py / evaluate.py.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "b" * 64
OBJECT_ID = "OBJ-KR055-CONCRETE-CLASS"

_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


@pytest.fixture(scope="module")
def rule() -> dict[str, object]:
    payload = _REGISTRY.get("KR-055")
    assert payload["coverage"] == "executable", "KR-055 должен быть executable"
    return payload


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    p = ((x, y), (x + 0.12, y), (x + 0.12, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=p, polygon_norm=p)


def _line(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(w, 0.05 + i * 0.14) for i, w in enumerate(words))


def _doc(stage: DocStage) -> DocumentRef:
    return DocumentRef(
        file_id=f"kr055-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"KR-055-TEST-{stage.value}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
    )


def _page(stage: DocStage, *words: str) -> StagePage:
    return StagePage(document=_doc(stage), tokens=_line(*words))


def _completeness_pd_rd() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


# ── основные сценарии ───────────────────────────────────────────────────────────────

def test_kr055_is_executable() -> None:
    """КР-055 должен быть отмечен executable в матрице."""
    assert _REGISTRY.get("KR-055")["coverage"] == "executable"
    assert _REGISTRY.get("KR-055")["extractor"]["type"] == "enum"
    assert _REGISTRY.get("KR-055")["comparator"]["operator"] == "class_not_lower"


def test_kr055_same_class_gives_no_difference(rule: dict[str, object]) -> None:
    """B25 == B25 → AUTO_NO_DIFFERENCE (класс не понижен)."""
    pages = {
        DocStage.PD: _page(DocStage.PD, "Класс", "бетона", "B25"),
        DocStage.RD: _page(DocStage.RD, "Класс", "бетона", "B25"),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness_pd_rd(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.evidence_group_id is not None
    assert result.evidence_group is not None
    assert len(result.evidence_group.fragments) == 2
    for fragment in result.evidence_group.fragments:
        assert fragment.page >= 1
        assert fragment.extracted.grounded_in_source_tokens
        assert fragment.extracted.second_read_agrees is True


def test_kr055_lower_class_in_rd_gives_candidate(rule: dict[str, object]) -> None:
    """PD=B30, RD=B25 (понижение) → CANDIDATE, не CONFIRMED_VIOLATION."""
    pages = {
        DocStage.PD: _page(DocStage.PD, "Класс", "бетона", "B30"),
        DocStage.RD: _page(DocStage.RD, "Класс", "бетона", "B25"),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness_pd_rd(),
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.evidence_group_id is not None


def test_kr055_higher_class_in_rd_is_not_violation(rule: dict[str, object]) -> None:
    """PD=B25, RD=B30 (повышение класса) → AUTO_NO_DIFFERENCE."""
    pages = {
        DocStage.PD: _page(DocStage.PD, "Класс", "бетона", "B25"),
        DocStage.RD: _page(DocStage.RD, "Класс", "бетона", "B30"),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness_pd_rd(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_kr055_b22_5_parsed_correctly(rule: dict[str, object]) -> None:
    """B22.5 парсится как B22.5, а не B22: сравнение B22.5 vs B22.5 → AUTO."""
    pages = {
        DocStage.PD: _page(DocStage.PD, "Класс", "бетона", "B22.5"),
        DocStage.RD: _page(DocStage.RD, "Класс", "бетона", "B22.5"),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness_pd_rd(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_kr055_rd_absent_gives_missing_evidence(rule: dict[str, object]) -> None:
    """РД не представлен → MISSING_EVIDENCE, missing_stage=RD."""
    pages = {
        DocStage.PD: _page(DocStage.PD, "Класс", "бетона", "B30"),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.missing_stage is DocStage.RD
    assert result.finding.evidence_group_id is None


def test_kr055_no_anchor_gives_low_quality(rule: dict[str, object]) -> None:
    """Токены без якоря "Класс бетона" → LOW_QUALITY (LOW_QUALITY ≠ нарушение)."""
    pages = {
        DocStage.PD: _page(DocStage.PD, "Таблица", "материалов", "B30"),
        DocStage.RD: _page(DocStage.RD, "Таблица", "элементов", "B25"),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness_pd_rd(),
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.evidence_group_id is None


def test_kr055_rd_head_is_kj_volume_not_ov(rule: dict[str, object]) -> None:
    """РД правила КР — марка КЖ из sources.rd.discipline, не соседний том ОВ."""

    def headed(
        stage: DocStage, file_id: str, code: str, *words: str
    ) -> tuple[StagePage, DocumentRef]:
        document = replace(_doc(stage), file_id=file_id, document_code=code)
        return StagePage(document=document, tokens=_line(*words)), document

    pd_kr, doc_pd = headed(DocStage.PD, "pd-kr", "АНО/150321/1-П-КР", "Класс", "бетона", "B35")
    pd_ar, doc_ar = headed(DocStage.PD, "pd-ar", "АНО/150321/1-П-АР", "Класс", "бетона", "B15")
    rd_kj, doc_kj = headed(DocStage.RD, "rd-kj", "АНО/150321/1-РД-КЖ", "Класс", "бетона", "B30")
    rd_ov, doc_ov = headed(DocStage.RD, "rd-ov", "АНО/150321/1-РД-ОВ1", "Класс", "бетона", "B10")
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={DocStage.PD: (pd_ar, pd_kr), DocStage.RD: (rd_ov, rd_kj)},
        completeness=_completeness_pd_rd(),
        revision_pool=[doc_ar, doc_pd, doc_ov, doc_kj],
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.source_id == "pd-kr"
    assert result.evidence_group is not None
    assert {item.document.file_id for item in result.evidence_group.fragments} == {
        "pd-kr",
        "rd-kj",
    }
