"""Д1: фикстуры экстрактора конкурсного среза. Не прирост 83 executable.

equal, mismatch, missing source, not approved, revision conflict,
OCR disagreement, unit conversion, соседнее нерелевантное число.
Автомат не пишет CONFIRMED_VIOLATION. мм→м только при явном суффиксе.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken, extract_number
from kontur.application.normalize import scale_length_to_target
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "d" * 64
OBJECT_ID = "OBJ-D1-FIXTURES"
_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str, x: float, y: float) -> PageToken:
    polygon = ((x, y), (x + 0.10, y), (x + 0.10, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _line(*words: str, y: float = 0.40) -> tuple[PageToken, ...]:
    return tuple(_tok(word, 0.06 + index * 0.13, y) for index, word in enumerate(words))


def _doc(stage: DocStage, *, file_id: str | None = None) -> DocumentRef:
    return DocumentRef(
        file_id=file_id or f"d1-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"D1-{stage.value}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
    )


def _page(
    stage: DocStage,
    tokens: tuple[PageToken, ...],
    *,
    file_id: str | None = None,
) -> StagePage:
    return StagePage(document=_doc(stage, file_id=file_id), tokens=tokens)


def _completeness(*, rd: Completeness = Completeness.UPLOADED) -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: rd,
        DocStage.ID: Completeness.MISSING,
    }


def test_scale_does_not_treat_bare_thousand_as_millimetres() -> None:
    assert scale_length_to_target(1200.0, source_unit=None, target_unit="м") == 1200.0
    assert scale_length_to_target(1200.0, source_unit="мм", target_unit="м") == 1.2
    assert scale_length_to_target(1.2, source_unit="м", target_unit="мм") == 1200.0
    assert scale_length_to_target(200.0, source_unit="мм", target_unit="мм") == 200.0


def test_pz001_equal_and_mismatch() -> None:
    rule = _REGISTRY.get("PZ-001")
    equal = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, _line("Площадь", "застройки", "1250,5")),
            DocStage.RD: _page(DocStage.RD, _line("Площадь", "застройки", "1 250,50")),
        },
        completeness=_completeness(),
    )
    assert equal.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    mismatch = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, _line("Площадь", "застройки", "1250,5")),
            DocStage.RD: _page(DocStage.RD, _line("Площадь", "застройки", "1100")),
        },
        completeness=_completeness(),
    )
    assert mismatch.finding.finding_status is FindingStatus.CANDIDATE
    assert mismatch.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_pz001_missing_source_is_not_violation() -> None:
    rule = _REGISTRY.get("PZ-001")
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={DocStage.PD: _page(DocStage.PD, _line("Площадь", "застройки", "1250,5"))},
        completeness=_completeness(rd=Completeness.MISSING),
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.finding.finding_status is not FindingStatus.CANDIDATE


def test_pz001_not_approved_and_revision_conflict() -> None:
    rule = _REGISTRY.get("PZ-001")
    blocked = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: StagePage(
                document=replace(_doc(DocStage.PD), approval_status=ApprovalStatus.NOT_APPROVED),
                tokens=_line("Площадь", "застройки", "1250,5"),
            ),
            DocStage.RD: _page(DocStage.RD, _line("Площадь", "застройки", "1100")),
        },
        completeness=_completeness(),
    )
    assert blocked.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    first = replace(_doc(DocStage.PD, file_id="pd-v1"), document_code="11111-PZ")
    second = replace(_doc(DocStage.PD, file_id="pd-v2"), document_code="11111-PZ")
    rd = _doc(DocStage.RD)
    conflict = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: (
                StagePage(document=first, tokens=_line("Площадь", "застройки", "1250,5")),
                StagePage(document=second, tokens=_line("Площадь", "застройки", "1100")),
            ),
            DocStage.RD: StagePage(document=rd, tokens=_line("Площадь", "застройки", "1100")),
        },
        completeness=_completeness(),
        revision_pool=[first, second, rd],
    )
    assert conflict.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert "несколько" in conflict.finding.rationale


def test_pz001_ocr_disagreement_and_neighbor_number() -> None:
    rule = _REGISTRY.get("PZ-001")
    disagree = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(
                DocStage.PD, _line("Площадь", "застройки", "1250,5", "1100")
            ),
            DocStage.RD: _page(DocStage.RD, _line("Площадь", "застройки", "1250,5")),
        },
        completeness=_completeness(),
    )
    assert disagree.finding.finding_status is FindingStatus.ABSTAIN
    neighbor = _line("Площадь", "участка", "9999", y=0.18) + _line(
        "Площадь", "застройки", "1250,5", y=0.42
    )
    hit = extract_number(neighbor, rule)
    assert hit is not None
    assert hit.extraction.normalized_value == 1250.5
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, neighbor),
            DocStage.RD: _page(DocStage.RD, _line("Площадь", "застройки", "1250,5")),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_ar041_mm_converts_to_metres_when_suffix_present() -> None:
    rule = _REGISTRY.get("AR-041")
    pd = _line("Ширина", "проема", "1200", "мм")
    rd = _line("Ширина", "проема", "1,2", "м")
    hit_pd = extract_number(pd, rule)
    hit_rd = extract_number(rd, rule)
    assert hit_pd is not None and hit_rd is not None
    assert hit_pd.extraction.normalized_value == 1.2
    assert hit_rd.extraction.normalized_value == 1.2
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, pd),
            DocStage.RD: _page(DocStage.RD, rd),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_ar041_bare_1200_is_not_guessed_as_millimetres() -> None:
    rule = _REGISTRY.get("AR-041")
    hit = extract_number(_line("Ширина", "проема", "1200"), rule)
    assert hit is not None
    assert hit.extraction.normalized_value == 1200.0


def test_kr055_equal_mismatch_and_neighbor_class() -> None:
    rule = _REGISTRY.get("KR-055")
    equal = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, _line("Класс", "бетона", "B30")),
            DocStage.RD: _page(DocStage.RD, _line("Класс", "бетона", "B30")),
        },
        completeness=_completeness(),
    )
    assert equal.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    mismatch = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, _line("Класс", "бетона", "B30")),
            DocStage.RD: _page(DocStage.RD, _line("Класс", "бетона", "B25")),
        },
        completeness=_completeness(),
    )
    assert mismatch.finding.finding_status is FindingStatus.CANDIDATE
    neighbor = _line("Класс", "ответственности", "C0", y=0.18) + _line(
        "Класс", "бетона", "B30", y=0.42
    )
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, neighbor),
            DocStage.RD: _page(DocStage.RD, _line("Класс", "бетона", "B30")),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_zu125_millimetres_stay_millimetres() -> None:
    rule = _REGISTRY.get("ZU-125")
    hit = extract_number(
        _line("Толщина", "утеплителя", "наружных", "стен", "200", "мм"),
        rule,
    )
    assert hit is not None
    assert hit.extraction.normalized_value == 200.0
