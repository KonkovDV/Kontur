"""Выбор якоря: плотность, ноль-шаблон, чужой норматив. Пороги gold не участвуют."""

from __future__ import annotations

from kontur.application.extractors.number import PageToken, extract_number


def _tok(text: str, x: float, y: float) -> PageToken:
    polygon = ((x, y), (x + 0.08, y), (x + 0.08, y + 0.03), (x, y + 0.03))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _rule(*, refs: list[object] | None = None) -> dict[str, object]:
    rule: dict[str, object] = {
        "code": "PZ-TEST",
        "unit": "м²",
        "extractor": {
            "type": "number",
            "anchors": ["площадь здания"],
            "dual_read_required": True,
        },
        "comparator": {"unit_target": "м²"},
    }
    if refs is not None:
        rule["normative_refs"] = refs
    return rule


def test_later_anchor_with_number_beats_legend_without_number() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.10),
        _tok("здания", 0.14, 0.10),
        _tok("5.", 0.05, 0.40),
        _tok("площадь", 0.14, 0.40),
        _tok("здания", 0.23, 0.40),
        _tok("25036,27", 0.32, 0.40),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 25036.27


def test_zero_placeholder_loses_to_another_anchor() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.20),
        _tok("здания", 0.14, 0.20),
        _tok("0", 0.23, 0.20),
        _tok("площадь", 0.05, 0.50),
        _tok("здания", 0.14, 0.50),
        _tok("25036,27", 0.23, 0.50),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 25036.27


def test_lone_zero_is_kept() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.20),
        _tok("здания", 0.14, 0.20),
        _tok("0", 0.23, 0.20),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 0.0


def test_foreign_standard_loses_when_rule_names_one() -> None:
    refs = [{"identifier": "СП 54.13330.2016", "clause": ""}]
    tokens = (
        _tok("площадь", 0.05, 0.20),
        _tok("здания", 0.14, 0.20),
        _tok("16867", 0.23, 0.20),
        _tok("СП", 0.32, 0.20),
        _tok("118.13330.2012", 0.41, 0.20),
        _tok("площадь", 0.05, 0.50),
        _tok("здания", 0.14, 0.50),
        _tok("25036", 0.23, 0.50),
        _tok("СП", 0.32, 0.50),
        _tok("54.13330.2016", 0.41, 0.50),
    )
    hit = extract_number(tokens, _rule(refs=refs))
    assert hit is not None
    assert hit.extraction.normalized_value == 25036.0


def test_standard_in_the_window_does_not_matter_without_rule_refs() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.20),
        _tok("здания", 0.14, 0.20),
        _tok("10", 0.23, 0.20),
        _tok("СП", 0.32, 0.20),
        _tok("118.13330.2012", 0.41, 0.20),
        _tok("площадь", 0.05, 0.50),
        _tok("здания", 0.14, 0.50),
        _tok("20", 0.23, 0.50),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 10.0


def test_value_before_label_beats_parenthetical_after() -> None:
    tokens = (
        _tok("1076,49", 0.02, 0.30),
        _tok("2.", 0.12, 0.30),
        _tok("площадь", 0.22, 0.30),
        _tok("здания", 0.32, 0.30),
        _tok("(порог", 0.42, 0.30),
        _tok("4,5", 0.52, 0.30),
        _tok("м)", 0.62, 0.30),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 1076.49
    assert hit.extraction.second_read_agrees is True


def test_cell_after_label_ignores_parenthetical_as_second_read() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.30),
        _tok("здания", 0.15, 0.30),
        _tok("1076,49", 0.25, 0.30),
        _tok("(порог", 0.35, 0.30),
        _tok("4,5", 0.45, 0.30),
        _tok("м)", 0.55, 0.30),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 1076.49
    assert hit.extraction.second_read_agrees is True


def test_number_after_label_beats_a_different_number_before_it() -> None:
    tokens = (
        _tok("100", 0.02, 0.30),
        _tok("площадь", 0.12, 0.30),
        _tok("здания", 0.22, 0.30),
        _tok("200", 0.32, 0.30),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 200.0


def test_parenthetical_is_kept_when_it_is_the_only_number() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.30),
        _tok("здания", 0.15, 0.30),
        _tok("(порог", 0.25, 0.30),
        _tok("4,5", 0.35, 0.30),
        _tok("м)", 0.45, 0.30),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 4.5


def test_numbered_row_wins_when_the_gap_is_equal() -> None:
    tokens = (
        _tok("площадь", 0.05, 0.20),
        _tok("здания", 0.14, 0.20),
        _tok("10", 0.23, 0.20),
        _tok("5.", 0.05, 0.50),
        _tok("площадь", 0.14, 0.50),
        _tok("здания", 0.23, 0.50),
        _tok("20", 0.32, 0.50),
    )
    hit = extract_number(tokens, _rule())
    assert hit is not None
    assert hit.extraction.normalized_value == 20.0
