"""Поведения образца room_pass на живых функциях.

Числовые пороги IOS4 здесь не читаются: у образца свой regex метки.
`protocol_status=CANDIDATE` в схему ответа не входит.
"""

from __future__ import annotations

from kontur.application.evaluate import StagePage, evaluate_free_search
from kontur.application.extractors.number import PageToken
from kontur.application.room_compare import compare_room_tokens, label_text
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import FindingStatus
from kontur.evaluation.submission import (
    ContestProtocolStatus,
    ContestViolationLabel,
    build_check,
)

HASH = "b" * 64


def _box(x: float, y: float) -> tuple[tuple[float, float], ...]:
    return ((x, y), (x + 0.01, y), (x + 0.01, y + 0.01), (x, y + 0.01))


def _token(text: str, x: float, y: float, page: int = 88) -> PageToken:
    polygon = _box(x, y)
    return PageToken(text=text, page=page, polygon_source=polygon, polygon_norm=polygon)


def _settings(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "room_regex": r"^(?:\d{3})$",
        "feature_regex": r"^В\d{1,2}$",
        "bind_radius": 0.05,
        "pair_jaccard_min": 0.5,
        "max_differences": 12,
    }
    raw.update(overrides)
    return raw


def _pd() -> tuple[PageToken, ...]:
    return (
        _token("140", 0.20, 0.20),
        _token("B4", 0.21, 0.23),
        _token("142", 0.50, 0.20),
        _token("В4", 0.51, 0.23),
        _token("147", 0.80, 0.20),
    )


def _rd(extra: tuple[PageToken, ...] = ()) -> tuple[PageToken, ...]:
    return (
        _token("140", 0.20, 0.20, page=18),
        _token("142", 0.50, 0.20, page=18),
        _token("В4", 0.51, 0.23, page=18),
        _token("147", 0.80, 0.20, page=18),
        *extra,
    )


def test_homoglyph_b_and_stripped_pe() -> None:
    assert label_text("B4") == "В4"
    assert label_text(" П 2 ") == "П 2"
    assert label_text("P2") == "П2"


def test_missing_feature_is_one_candidate() -> None:
    diffs = compare_room_tokens(_pd(), _rd(), _settings())
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["140"] == "candidate"
    assert "142" not in kinds
    assert "147" not in kinds


def test_shared_feature_is_not_a_candidate() -> None:
    rd = _rd((_token("В4", 0.21, 0.23, page=18),))
    diffs = compare_room_tokens(_pd(), rd, _settings())
    assert all(item.kind != "candidate" for item in diffs)


def test_duplicate_room_abstains_that_room() -> None:
    rd = _rd((_token("140", 0.90, 0.90, page=18),))
    diffs = compare_room_tokens(_pd(), rd, _settings())
    assert any(item.room == "140" and item.kind == "abstain" for item in diffs)


def test_unrelated_sheet_is_ignored() -> None:
    rd = _rd() + (
        _token("600", 0.2, 0.2, page=17),
        _token("601", 0.5, 0.5, page=17),
    )
    diffs = compare_room_tokens(_pd(), rd, _settings())
    rooms = {item.room for item in diffs}
    assert "140" in rooms
    assert "600" not in rooms


def test_ambiguous_feature_is_not_a_candidate() -> None:
    pd = (
        _token("140", 0.20, 0.20),
        _token("141", 0.24, 0.20),
        _token("В4", 0.22, 0.23),
        _token("142", 0.5, 0.5),
    )
    rd = (
        _token("140", 0.20, 0.20, page=18),
        _token("141", 0.24, 0.20, page=18),
        _token("142", 0.5, 0.5, page=18),
    )
    diffs = compare_room_tokens(pd, rd, _settings())
    assert all(item.kind != "candidate" for item in diffs)


def test_too_many_diffs_abstain_the_pair() -> None:
    diffs = compare_room_tokens(_pd(), _rd(), _settings(max_differences=0))
    assert len(diffs) == 1
    assert diffs[0].kind == "abstain"


def test_exclude_bbox_drops_the_room_inside_it() -> None:
    settings = _settings(
        exclude_bboxes=[[0.15, 0.15, 0.30, 0.30]],
    )
    diffs = compare_room_tokens(_pd(), _rd(), settings)
    assert all(item.room != "140" for item in diffs)


def test_free_search_suspicion_is_warning_on_the_wire() -> None:
    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "review_priority": "MEDIUM",
        "extractor": {"type": "room_compare", "room_compare": _settings()},
    }
    doc = DocumentRef(
        file_id="f-pd",
        file_hash=HASH,
        doc_stage=DocStage.PD,
        document_code="ОВ",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )
    rd_doc = DocumentRef(
        file_id="f-rd",
        file_hash=HASH,
        doc_stage=DocStage.RD,
        document_code="ОВ",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
    )
    pages = {
        DocStage.PD: StagePage(document=doc, tokens=_pd()),
        DocStage.RD: StagePage(document=rd_doc, tokens=_rd()),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    assert found
    assert found[0].finding.finding_status is FindingStatus.SUSPICION
    check = build_check(
        found[0].finding,
        found[0].evidence_group,
        known_codes=["FREE-HEATING-001"],
    )
    assert check.violation_label is ContestViolationLabel.VIOLATION_PRESENT
    assert check.protocol_status is ContestProtocolStatus.WARNING
    assert check.location == "140"
