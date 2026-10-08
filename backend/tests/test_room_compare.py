"""Сравнение помещений на токенах. Пороги из правила, не из gold."""

from __future__ import annotations

from kontur.application.evaluate import StagePage, _room_rule, evaluate_free_search, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.room_compare import compare_room_tokens
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef, ExtractionEngine
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.evaluation.submission import location_from_group
from kontur.infrastructure.matrix.free_search import load_free_search
from kontur.infrastructure.matrix.registry import FileRuleRegistry, discover_matrix_root

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


def _doc(stage: DocStage, file_id: str | None = None, code: str = "ОВ") -> DocumentRef:
    return DocumentRef(
        file_id=file_id or f"f-{stage.value}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=code,
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


def test_room_only_on_pd_is_suspicion() -> None:
    pd = (
        _token("101", 0.2, 0.2),
        _token("В", 0.23, 0.2),
        _token("104", 0.4, 0.4),
    )
    rd = (_token("101", 0.2, 0.2), _token("В", 0.23, 0.2))
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "suspicion" and item.room == "104" for item in diffs)


def test_feature_only_on_rd_is_suspicion() -> None:
    pd = (_token("101", 0.2, 0.2),)
    rd = (_token("101", 0.2, 0.2), _token("В", 0.23, 0.2))
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "suspicion" and item.room == "101" for item in diffs)


def test_duplicate_does_not_steal_another_sheet() -> None:
    pd = (
        _token("101", 0.2, 0.2, page=1),
        _token("101", 0.6, 0.6, page=1),
        _token("201", 0.2, 0.2, page=2),
        _token("В", 0.23, 0.2, page=2),
        _token("202", 0.5, 0.5, page=2),
    )
    rd = (
        _token("201", 0.2, 0.2, page=5),
        _token("202", 0.5, 0.5, page=5),
        _token("101", 0.2, 0.2, page=9),
    )
    diffs = compare_room_tokens(pd, rd, _settings())
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["201"] == "candidate"
    assert any(item.kind == "abstain" for item in diffs)


def test_glued_room_token_splits_and_section_does_not() -> None:
    pd = (_token("001.1001.1", 0.2, 0.2), _token("500×300", 0.5, 0.5))
    rd = (_token("001.1", 0.2, 0.2),)
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "abstain" for item in diffs)
    assert all(item.room != "500" for item in diffs)
    assert all(item.room != "300" for item in diffs)


def test_fragment_keeps_source_polygon_and_ocr_engine() -> None:
    rule = dict(FileRuleRegistry().get("IOS4-078"))
    extractor = dict(rule["extractor"])  # type: ignore[arg-type]
    extractor["type"] = "room_compare"
    rule["extractor"] = extractor
    source = ((10.0, 20.0), (30.0, 20.0), (30.0, 40.0), (10.0, 40.0))
    norm = _box(0.2, 0.2)
    room = PageToken(
        text="140",
        page=1,
        polygon_source=source,
        polygon_norm=norm,
        engine=ExtractionEngine.OCR,
    )
    pd = StagePage(document=_doc(DocStage.PD), tokens=(room, _token("В", 0.23, 0.2)))
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
    assert location_from_group(result.evidence_group) == "140"
    fragment = result.evidence_group.fragments[0]
    assert fragment.polygon_source == source
    assert fragment.polygon_norm == norm
    assert fragment.extracted.engine is ExtractionEngine.OCR


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
    assert location_from_group(rooms[0].evidence_group) == "140"


def test_two_by_two_volumes_keep_the_best_room_pair() -> None:
    rule = FileRuleRegistry().get("IOS4-078")
    pages = {
        DocStage.PD: (
            StagePage(
                document=_doc(DocStage.PD, "pd-a", "ОВ-A"),
                tokens=(
                    _token("101", 0.2, 0.2),
                    _token("В", 0.23, 0.2),
                    _token("102", 0.5, 0.5),
                    _token("В", 0.53, 0.5),
                ),
            ),
            StagePage(
                document=_doc(DocStage.PD, "pd-b", "ОВ-B"),
                tokens=(_token("901", 0.2, 0.2), _token("В", 0.23, 0.2)),
            ),
        ),
        DocStage.RD: (
            StagePage(
                document=_doc(DocStage.RD, "rd-a", "ОВ-A"),
                tokens=(
                    _token("101", 0.2, 0.2),
                    _token("102", 0.5, 0.5),
                    _token("В", 0.53, 0.5),
                ),
            ),
            StagePage(
                document=_doc(DocStage.RD, "rd-b", "ОВ-B"),
                tokens=(_token("404", 0.2, 0.2), _token("В", 0.23, 0.2)),
            ),
        ),
    }
    result = _room_rule(rule, pages, "OBJ-ROOM")
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.evidence_group is not None
    assert result.evidence_group.fragments[0].room_id == "101"
    assert {item.document.file_id for item in result.evidence_group.fragments} == {"pd-a", "rd-a"}


def test_disjoint_volume_pairs_both_compare() -> None:
    rule = FileRuleRegistry().get("IOS4-078")
    pages = {
        DocStage.PD: (
            StagePage(
                document=_doc(DocStage.PD, "pd-a", "ОВ-A"),
                tokens=(_token("101", 0.2, 0.2), _token("В", 0.23, 0.2)),
            ),
            StagePage(
                document=_doc(DocStage.PD, "pd-b", "ОВ-B"),
                tokens=(_token("202", 0.2, 0.2), _token("В", 0.23, 0.2)),
            ),
        ),
        DocStage.RD: (
            StagePage(
                document=_doc(DocStage.RD, "rd-a", "ОВ-A"),
                tokens=(_token("101", 0.2, 0.2),),
            ),
            StagePage(
                document=_doc(DocStage.RD, "rd-b", "ОВ-B"),
                tokens=(_token("202", 0.2, 0.2),),
            ),
        ),
    }
    result = _room_rule(rule, pages, "OBJ-ROOM")
    rooms: list[str] = []
    for item in (result, *result.also):
        group = item.evidence_group
        if group is None:
            continue
        rooms.append(group.fragments[0].room_id or "")
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert sorted(rooms) == ["101", "202"]


def test_free_search_room_diff_stays_suspicion() -> None:
    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=(_token("101", 0.2, 0.2), _token("В", 0.23, 0.2)),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(_token("101", 0.2, 0.2),),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    assert len(found) == 1
    assert found[0].finding.finding_status is FindingStatus.SUSPICION
    assert found[0].evidence_group is not None
    assert found[0].evidence_group.fragments[0].room_id == "101"


def test_branch_mark_with_decimal_binds_to_the_room() -> None:
    pd = (_token("140", 0.20, 0.40), _token("В2.9", 0.28, 0.40))
    rd = (_token("140", 0.20, 0.40),)
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "candidate" and item.room == "140" for item in diffs)


def test_latin_b_matches_cyrillic_feature_regex() -> None:
    pd = (_token("101", 0.2, 0.2), _token("B", 0.23, 0.2))
    rd = (_token("101", 0.2, 0.2),)
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "candidate" and item.room == "101" for item in diffs)


def test_one_rd_sheet_does_not_drop_the_second_pd_sheet() -> None:
    pd = (
        _token("101", 0.2, 0.2, page=1),
        _token("В", 0.23, 0.2, page=1),
        _token("202", 0.2, 0.2, page=2),
        _token("В", 0.23, 0.2, page=2),
    )
    rd = (
        _token("101", 0.2, 0.2, page=9),
        _token("202", 0.5, 0.5, page=9),
    )
    kinds = {item.room: item.kind for item in compare_room_tokens(pd, rd, _settings())}
    assert kinds["101"] == "candidate"
    assert kinds["202"] == "candidate"


def test_unrelated_sheet_does_not_emit_its_rooms() -> None:
    pd = (
        _token("101", 0.2, 0.2, page=1),
        _token("В", 0.23, 0.2, page=1),
        _token("102", 0.5, 0.5, page=1),
    )
    rd = (
        _token("101", 0.2, 0.2, page=2),
        _token("600", 0.2, 0.2, page=3),
        _token("601", 0.5, 0.5, page=3),
    )
    kinds = {item.room: item.kind for item in compare_room_tokens(pd, rd, _settings())}
    assert kinds["101"] == "candidate"
    assert "600" not in kinds
    assert "601" not in kinds


def test_conflicting_pairs_abstain_that_room_only() -> None:
    pd = (
        _token("101", 0.2, 0.2, page=1),
        _token("В", 0.23, 0.2, page=1),
        _token("202", 0.2, 0.2, page=2),
        _token("В", 0.23, 0.2, page=2),
        _token("101", 0.2, 0.2, page=3),
        _token("В", 0.23, 0.2, page=3),
    )
    rd = (
        _token("101", 0.2, 0.2, page=5),
        _token("202", 0.2, 0.2, page=6),
        _token("101", 0.2, 0.2, page=7),
        _token("В", 0.23, 0.2, page=7),
    )
    kinds = {item.room: item.kind for item in compare_room_tokens(pd, rd, _settings())}
    assert kinds["101"] == "abstain"
    assert kinds["202"] == "candidate"


def test_split_room_and_feature_tokens_join_before_compare() -> None:
    pd = (
        _token("14", 0.20, 0.20),
        _token("0", 0.222, 0.20),
        _token("В", 0.25, 0.20),
        _token("2", 0.272, 0.20),
    )
    rd = (
        _token("14", 0.20, 0.20),
        _token("0", 0.222, 0.20),
    )
    diffs = compare_room_tokens(pd, rd, _settings())
    assert any(item.kind == "candidate" and item.room == "140" for item in diffs)


def test_split_heating_label_reaches_free_search_with_room_location() -> None:
    entry = load_free_search(discover_matrix_root() / "free_search.json")[0]
    assert entry.parameter_code == "FREE-HEATING-001"
    assert entry.room_compare is not None
    rule = {
        "code": entry.parameter_code,
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "room_compare": entry.room_compare},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=(
                _token("267", 0.20, 0.20),
                _token("тёплый", 0.25, 0.20),
                _token("пол", 0.275, 0.20),
            ),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(_token("267", 0.20, 0.20),),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    assert len(found) == 1
    assert found[0].finding.finding_status is FindingStatus.SUSPICION
    group = found[0].evidence_group
    assert group is not None
    assert location_from_group(group) == "267"


def _words(*parts: str, y: float = 0.30) -> tuple[PageToken, ...]:
    return tuple(_token(part, 0.05 + index * 0.08, y) for index, part in enumerate(parts))


def test_project_clause_is_a_suspicion_when_rd_never_names_the_element() -> None:
    entry = load_free_search(discover_matrix_root() / "free_search.json")[0]
    assert entry.provision is True
    rule = {
        "code": entry.parameter_code,
        "matrix_version": "draft-0",
        "review_priority": "HIGH",
        "extractor": {
            "type": "room_compare",
            "room_compare": entry.room_compare,
            "provision": True,
        },
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD, "pd-note"),
            tokens=_words(
                "В",
                "помещениях",
                "(пом.",
                "267,",
                "270)",
                "предусмотрена",
                "система",
                "подогрева",
                "полов",
                "(теплые",
                "полы).",
            ),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD, "rd-plan"),
            tokens=(_token("267", 0.20, 0.40), _token("270", 0.40, 0.40)),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    rooms = {location_from_group(item.evidence_group) for item in found if item.evidence_group}
    assert rooms == {"267", "270"}
    assert all(item.finding.finding_status is FindingStatus.SUSPICION for item in found)


def test_split_room_list_in_one_token_still_names_every_room() -> None:
    """Как в томе 5.4.2: «(пом. 267, 270,» и «271, 272)» — два куска, четыре номера."""

    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "provision": True, "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=_words(
                "(пом. 267, 270,",
                "271, 272)",
                "предусмотрена",
                "система",
                "подогрева",
                "полов",
                "(теплые",
                "полы)",
                "совмещенная",
                "с",
                "системой",
                "радиаторного",
                "отопления.",
            ),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(
                _token("267", 0.20, 0.40),
                _token("270", 0.30, 0.40),
                _token("271", 0.40, 0.40),
                _token("272", 0.50, 0.40),
                _token("отопления", 0.20, 0.80, page=2),
            ),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    rooms = {location_from_group(item.evidence_group) for item in found if item.evidence_group}
    assert rooms == {"267", "270", "271", "272"}


def test_wrapped_room_list_keeps_the_numbers_from_the_next_line() -> None:
    """Перенос строки рвёт «267, 270,» и «271, 272)» и вставляет чужую фразу между ними."""

    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "provision": True, "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=(
                _token("(пом. 267, 270,", 0.70, 0.30),
                _token("В помещениях раздевальных", 0.10, 0.315),
                _token("271, 272)", 0.05, 0.34),
                _token("предусмотрена", 0.20, 0.34),
                _token("система", 0.35, 0.34),
                _token("подогрева", 0.45, 0.34),
                _token("полов.", 0.55, 0.34),
            ),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(
                _token("267", 0.20, 0.40),
                _token("270", 0.30, 0.40),
                _token("271", 0.40, 0.40),
                _token("272", 0.50, 0.40),
            ),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    rooms = {location_from_group(item.evidence_group) for item in found if item.evidence_group}
    assert rooms == {"267", "270", "271", "272"}


def test_other_pdf_page_in_the_same_file_does_not_break_the_clause() -> None:
    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "provision": True, "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=(
                _token("(пом. 267, 270,", 0.70, 0.30, page=11),
                _token("В помещениях раздевальных", 0.10, 0.32, page=99),
                _token("271, 272)", 0.05, 0.34, page=11),
                _token("предусмотрена", 0.20, 0.34, page=11),
                _token("система", 0.35, 0.34, page=11),
                _token("подогрева", 0.45, 0.34, page=11),
                _token("полов.", 0.55, 0.34, page=11),
            ),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(
                _token("267", 0.20, 0.40, page=17),
                _token("270", 0.30, 0.40, page=17),
                _token("271", 0.40, 0.40, page=17),
                _token("272", 0.50, 0.40, page=17),
            ),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    rooms = {location_from_group(item.evidence_group) for item in found if item.evidence_group}
    assert rooms == {"267", "270", "271", "272"}


def test_same_page_number_in_another_volume_does_not_erase_the_room() -> None:
    """Лист 17 чужого тома со словом «полов» не отменяет лист 17, где элемента нет."""

    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "provision": True, "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD, "pd-note"),
            tokens=_words("пом.", "267", "предусмотрена", "система", "подогрева", "полов."),
        ),
        DocStage.RD: (
            StagePage(
                document=_doc(DocStage.RD, "rd-other"),
                tokens=(_token("267", 0.20, 0.40), _token("полов", 0.40, 0.40)),
            ),
            StagePage(
                document=_doc(DocStage.RD, "rd-plan"),
                tokens=(_token("267", 0.20, 0.40),),
            ),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    rooms = {location_from_group(item.evidence_group) for item in found if item.evidence_group}
    assert rooms == {"267"}
    assert found[0].evidence_group is not None
    assert found[0].evidence_group.resolved_revisions[1].file_id == "rd-plan"


def test_project_clause_stays_quiet_when_rd_names_the_element() -> None:
    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "provision": True, "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=_words("пом.", "267", "предусмотрена", "система", "подогрева", "полов."),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(_token("267", 0.20, 0.40), _token("подогрева", 0.40, 0.40)),
        ),
    }
    found = evaluate_free_search(rule, pages, "OBJ-ROOM")
    assert found == ()


def test_design_assignment_infinitive_is_not_a_provision() -> None:
    rule = {
        "code": "FREE-HEATING-001",
        "matrix_version": "draft-0",
        "extractor": {"type": "room_compare", "provision": True, "room_compare": _settings()},
    }
    pages = {
        DocStage.PD: StagePage(
            document=_doc(DocStage.PD),
            tokens=_words("пом.", "267", "предусмотреть", "подогрев", "полов."),
        ),
        DocStage.RD: StagePage(
            document=_doc(DocStage.RD),
            tokens=(_token("267", 0.20, 0.40),),
        ),
    }
    assert evaluate_free_search(rule, pages, "OBJ-ROOM") == ()


def test_close_duplicate_is_one_inscription() -> None:
    pd = (
        _token("101", 0.20, 0.20),
        _token("101", 0.23, 0.21),
        _token("В", 0.26, 0.20),
    )
    rd = (_token("101", 0.20, 0.20),)
    diffs = compare_room_tokens(pd, rd, _settings())
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["101"] == "candidate"


def test_schedule_column_is_not_a_second_room() -> None:
    pd = (
        _token("110", 0.20, 0.20),
        _token("111", 0.20, 0.24),
        _token("112", 0.20, 0.28),
        _token("110", 0.70, 0.70),
        _token("В", 0.73, 0.70),
    )
    rd = (_token("110", 0.70, 0.70),)
    diffs = compare_room_tokens(pd, rd, _settings())
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["110"] == "candidate"
    assert "abstain" not in kinds.values()


def test_comma_list_shares_one_feature() -> None:
    settings = dict(_settings())
    settings["feature_regex"] = r"(?i)^т[её]плый\s+пол$"
    pd = (
        _token("271, 272", 0.30, 0.40),
        _token("теплый пол", 0.34, 0.40),
    )
    rd = (_token("271", 0.30, 0.40), _token("272", 0.50, 0.50))
    diffs = compare_room_tokens(pd, rd, settings)
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["271"] == "candidate"
    assert kinds["272"] == "candidate"


def test_shared_room_compares_when_sheets_do_not_pair() -> None:
    pd = [_token("140", 0.20, 0.20, page=1), _token("В", 0.23, 0.20, page=1)]
    rd = [_token("140", 0.20, 0.20, page=2)]
    for index in range(10):
        pd.append(_token(f"{200 + index}", 0.10, 0.10 + index * 0.05, page=1))
        rd.append(_token(f"{300 + index}", 0.10, 0.10 + index * 0.05, page=2))
    diffs = compare_room_tokens(tuple(pd), tuple(rd), _settings())
    kinds = {item.room: item.kind for item in diffs}
    assert kinds["140"] == "candidate"
    assert "300" not in kinds
    assert "200" not in kinds
