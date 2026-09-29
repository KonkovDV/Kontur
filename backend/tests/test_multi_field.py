"""Несколько явных единиц в одном пункте. Фигуры на листе не считаются."""

from __future__ import annotations

from pathlib import Path

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]


def _rule(code: str) -> dict[str, object]:
    return FileRuleRegistry(REPO / "data" / "matrix").get(code)


def _doc(stage: DocStage, code: str, file_id: str) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=f"{file_id.encode().hex():0<64}"[:64],
        doc_stage=stage,
        document_code=code,
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )


def _tok(text: str, x: float, y: float) -> PageToken:
    polygon = ((x, y), (x + 0.12, y), (x + 0.12, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _page(document: DocumentRef, pairs: tuple[tuple[str, str], ...]) -> StagePage:
    tokens = [_tok("1:100", 0.05, 0.90)]
    for index, (value, unit) in enumerate(pairs):
        y = 0.30 + index * 0.08
        tokens.append(_tok(value, 0.10, y))
        tokens.append(_tok(unit, 0.28, y))
    return StagePage(document=document, tokens=tuple(tokens))


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def test_same_material_bill_is_not_a_hit() -> None:
    pairs = (("120,5", "м³"), ("4,2", "т"))
    pd = _doc(DocStage.PD, "КР-1", "kr-pd")
    rd = _doc(DocStage.RD, "КР-1", "kr-rd")
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={DocStage.PD: _page(pd, pairs), DocStage.RD: _page(rd, pairs)},
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.evidence_group is not None


def test_steel_beyond_two_percent_is_a_candidate() -> None:
    pd = _doc(DocStage.PD, "КР-1", "kr-pd")
    rd = _doc(DocStage.RD, "КР-1", "kr-rd")
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={
            DocStage.PD: _page(pd, (("100", "м³"), ("4", "т"))),
            DocStage.RD: _page(rd, (("100", "м³"), ("4,2", "т"))),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.expected_value == 4.0
    assert result.finding.actual_value == 4.2


def test_concrete_within_two_percent_is_not_a_hit() -> None:
    pd = _doc(DocStage.PD, "КР-1", "kr-pd")
    rd = _doc(DocStage.RD, "КР-1", "kr-rd")
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={
            DocStage.PD: _page(pd, (("100", "м³"), ("4", "т"))),
            DocStage.RD: _page(rd, (("101", "м³"), ("4", "т"))),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_bare_number_is_not_a_field() -> None:
    pd = _doc(DocStage.PD, "КР-1", "kr-pd")
    rd = _doc(DocStage.RD, "КР-1", "kr-rd")
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={
            DocStage.PD: _page(pd, (("120,5", "м³"), ("4,2", "т"))),
            DocStage.RD: StagePage(document=rd, tokens=(_tok("120,5", 0.10, 0.30),)),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert "поле" in result.finding.rationale
    assert result.evidence_group is None


def test_repeated_unit_is_not_compared() -> None:
    pd = _doc(DocStage.PD, "КР-1", "kr-pd")
    page = StagePage(
        document=pd,
        tokens=(
            _tok("10", 0.10, 0.30),
            _tok("м³", 0.28, 0.30),
            _tok("12", 0.50, 0.30),
            _tok("м³", 0.68, 0.30),
            _tok("4", 0.10, 0.40),
            _tok("т", 0.28, 0.40),
        ),
    )
    rd = _doc(DocStage.RD, "КР-1", "kr-rd")
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={DocStage.PD: page, DocStage.RD: _page(rd, (("10", "м³"), ("4", "т")))},
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert "повторяется" in result.finding.rationale


def test_missing_material_stage_is_missing_evidence() -> None:
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.evidence_group is None


def test_two_pd_of_one_kr_cipher_are_not_compared() -> None:
    first = _doc(DocStage.PD, "КР-1", "kr-pd-1")
    second = _doc(DocStage.PD, "КР-1", "kr-pd-2")
    rd = _doc(DocStage.RD, "КР-1", "kr-rd")
    result = evaluate_rule(
        _rule("KR-067"),
        object_id="OBJ-KR-067",
        pages={DocStage.RD: _page(rd, (("120,5", "м³"), ("4,2", "т")))},
        completeness=_completeness(),
        revision_pool=[first, second, rd],
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.finding_status is not FindingStatus.MISSING_EVIDENCE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_window_schedule_reads_units_not_rectangles() -> None:
    pairs = (("12", "шт."), ("40", "м²"))
    pd = _doc(DocStage.PD, "П-АР1", "ar-pd")
    rd = _doc(DocStage.RD, "П-АР1", "ar-rd")
    same = evaluate_rule(
        _rule("AR-046"),
        object_id="OBJ-AR-046",
        pages={DocStage.PD: _page(pd, pairs), DocStage.RD: _page(rd, pairs)},
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert same.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    changed = evaluate_rule(
        _rule("AR-046"),
        object_id="OBJ-AR-046",
        pages={
            DocStage.PD: _page(pd, pairs),
            DocStage.RD: _page(rd, (("10", "шт."), ("40", "м²"))),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert changed.finding.finding_status is FindingStatus.CANDIDATE
    assert changed.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    unlabeled = evaluate_rule(
        _rule("AR-046"),
        object_id="OBJ-AR-046",
        pages={
            DocStage.PD: _page(pd, pairs),
            DocStage.RD: StagePage(document=rd, tokens=(_tok("12", 0.10, 0.30),)),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert unlabeled.finding.finding_status is FindingStatus.LOW_QUALITY


def test_parking_count_on_a_plan_stays_without_extractor() -> None:
    rule = _rule("SPZU-037")
    assert rule["coverage"] == "extractor_missing"
    extractor = rule["extractor"]
    assert isinstance(extractor, dict)
    assert extractor["type"] == "number"
