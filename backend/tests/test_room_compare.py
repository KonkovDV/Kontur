"""Сравнение помещений на токенах. Пороги из правила, не из gold."""

from __future__ import annotations

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.room_compare import compare_room_tokens
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.evaluation.submission import location_from_group
from kontur.infrastructure.matrix.registry import FileRuleRegistry

HASH = "a" * 64


def _box(x: float, y: float) -> tuple[tuple[float, float], ...]:
    return ((x, y), (x + 0.02, y), (x + 0.02, y + 0.02), (x, y + 0.02))


def _token(text: str, x: float, y: float, page: int = 1) -> PageToken:
    polygon = _box(x, y)
    return PageToken(text=text, page=page, polygon_source=polygon, polygon_norm=polygon)


def _settings() -> dict[str, object]:
    rule = FileRuleRegistry().get("IOS4-078")
    extractor = rule["extractor"]
    assert isinstance(extractor, dict)
    raw = extractor["room_compare"]
    assert isinstance(raw, dict)
    return raw


def _doc(stage: DocStage) -> DocumentRef:
    return DocumentRef(
        file_id=f"f-{stage.value}",
        file_hash=HASH,
        doc_stage=stage,
        document_code="ОВ",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )


def test_missing_feature_is_candidate_and_shared_feature_is_quiet() -> None:
    pd = (
        _token("101", 0.2, 0.2),
        _token("В", 0.23, 0.2),
        _token("102", 0.5, 0.5),
        _token("В", 0.53, 0.5),
    )
    rd = (
        _token("101", 0.2, 0.2),
        _token("102", 0.5, 0.5),
        _token("В", 0.53, 0.5),
    )
    diffs = compare_room_tokens(pd, rd, _settings())
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["101"] == "candidate"
    assert "102" not in kinds


def test_room_only_on_rd_is_suspicion() -> None:
    pd = (_token("101", 0.2, 0.2), _token("В", 0.23, 0.2))
    rd = (
        _token("101", 0.2, 0.2),
        _token("В", 0.23, 0.2),
        _token("103", 0.7, 0.7),
    )
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "suspicion" and item.room == "103" for item in diffs)


def test_duplicate_room_abstains() -> None:
    pd = (_token("101", 0.2, 0.2), _token("101", 0.6, 0.6))
    rd = (_token("101", 0.2, 0.2),)
    diffs = compare_room_tokens(pd, rd, _settings())
    assert [item.kind for item in diffs] == ["abstain"]


def test_same_tokens_do_not_depend_on_calling_twice() -> None:
    tokens = (_token("140", 0.2, 0.2), _token("В", 0.23, 0.2))
    first = compare_room_tokens(tokens, tokens, _settings())
    second = compare_room_tokens(tokens, tokens, _settings())
    assert [item.kind for item in first] == [item.kind for item in second] == ["match"]


def test_evaluate_puts_room_into_location() -> None:
    rule = dict(FileRuleRegistry().get("IOS4-078"))
    extractor = dict(rule["extractor"])  # type: ignore[arg-type]
    extractor["type"] = "room_compare"
    rule["extractor"] = extractor
    pd = StagePage(
        document=_doc(DocStage.PD),
        tokens=(_token("140", 0.2, 0.2), _token("В", 0.23, 0.2)),
    )
    rd = StagePage(document=_doc(DocStage.RD), tokens=(_token("140", 0.2, 0.2),))
    result = evaluate_rule(
        rule,
        object_id="OBJ-ROOM",
        pages={DocStage.PD: pd, DocStage.RD: rd},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.UPLOADED,
            DocStage.ID: Completeness.MISSING,
        },
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.evidence_group is not None
    assert result.evidence_group.fragments[0].room_id == "140"
    assert location_from_group(result.evidence_group) == "помещение 140"


def test_live_number_pass_keeps_section_and_adds_room() -> None:
    rule = FileRuleRegistry().get("IOS4-078")
    section = (
        _token("сечение", 0.10, 0.80),
        _token("воздуховода", 0.20, 0.80),
        _token("500×300", 0.40, 0.80),
    )
    pd = StagePage(
        document=_doc(DocStage.PD),
        tokens=section + (_token("140", 0.20, 0.20), _token("В", 0.23, 0.20)),
    )
    rd = StagePage(
        document=_doc(DocStage.RD),
        tokens=section + (_token("140", 0.20, 0.20),),
    )
    result = evaluate_rule(
        rule,
        object_id="OBJ-ROOM",
        pages={DocStage.PD: pd, DocStage.RD: rd},
        completeness={
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.UPLOADED,
            DocStage.ID: Completeness.MISSING,
        },
    )
    rooms = [item for item in result.also if item.finding.finding_status is FindingStatus.CANDIDATE]
    assert rooms
    assert rooms[0].evidence_group is not None
    assert rooms[0].evidence_group.fragments[0].room_id == "140"
    assert location_from_group(rooms[0].evidence_group) == "помещение 140"
