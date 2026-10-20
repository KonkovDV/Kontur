"""Пять ключевых полей штампа: найдено, нет, нечитаемо. Порог 0,90 не закрывается."""

from __future__ import annotations

from kontur.application.extractors.number import PageToken
from kontur.application.passport import KeyFieldState, stamp_key_fields


def _tok(text: str, x: float, y: float = 0.82) -> PageToken:
    polygon = ((x, y), (x + 0.16, y), (x + 0.16, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _states(fields):
    return (
        fields.cipher.state,
        fields.stage.state,
        fields.revision.state,
        fields.sheet.state,
        fields.room_element.state,
    )


def test_stage_letter_is_its_own_field() -> None:
    fields = stamp_key_fields((_tok("Стадия", 0.40), _tok("П", 0.62)))
    assert fields.stage.state is KeyFieldState.FOUND
    assert fields.stage.value == "PD"


def test_sheet_total_does_not_fill_the_sheet_field() -> None:
    fields = stamp_key_fields((_tok("листов 17", 0.70),))
    assert fields.sheet.state is KeyFieldState.ABSENT
    single = stamp_key_fields(
        (
            _tok("Лист", 0.40, 0.86),
            _tok("Листов", 0.65, 0.86),
            _tok("1", 0.65, 0.91),
        )
    )
    assert single.sheet.state is KeyFieldState.FOUND
    assert single.sheet.value == "1"
    inset = stamp_key_fields(
        (
            _tok("лист 2", 0.08, 0.72),
            _tok("лист 26", 0.78, 0.92),
        )
    )
    assert inset.sheet.state is KeyFieldState.FOUND
    assert inset.sheet.value == "26"


def test_a_standard_in_the_stamp_is_not_a_cipher() -> None:
    fields = stamp_key_fields((_tok("обозначение ГОСТ 21.101-2020", 0.40),))
    assert fields.cipher.state is KeyFieldState.ABSENT
    assert fields.cipher.value is None


def test_each_key_field_is_found_when_the_stamp_names_it() -> None:
    fields = stamp_key_fields(
        (
            _tok("шифр: 12345-PZ", 0.05),
            _tok("изм. 3", 0.28),
            _tok("лист 2", 0.46),
            _tok("стадия ПД", 0.64),
            _tok("пом. 267", 0.80),
        )
    )
    assert _states(fields) == (KeyFieldState.FOUND,) * 5
    assert fields.cipher.value == "12345-PZ"
    assert fields.stage.value == "PD"
    assert fields.revision.value == "3"
    assert fields.sheet.value == "2"
    assert fields.room_element.value == "267"


def test_missing_labels_are_absent_not_invented() -> None:
    fields = stamp_key_fields(())
    assert _states(fields) == (KeyFieldState.ABSENT,) * 5
    assert fields.cipher.value is None


def test_each_key_field_is_unreadable_when_two_readings_disagree() -> None:
    fields = stamp_key_fields(
        (
            _tok("шифр: 12345-PZ", 0.05),
            _tok("изм. 2", 0.24),
            _tok("изм. 4", 0.40),
            _tok("лист 1", 0.56),
            _tok("лист 2", 0.70),
            _tok("стадия ПД", 0.05, 0.90),
            _tok("пом. 267", 0.24, 0.90),
            _tok("пом. 270", 0.42, 0.90),
        ),
        filename="tom_RD.pdf",
        alternate_ciphers=("99999-AR",),
    )
    assert fields.cipher.state is KeyFieldState.UNREADABLE
    assert fields.stage.state is KeyFieldState.UNREADABLE
    assert fields.revision.state is KeyFieldState.UNREADABLE
    assert fields.sheet.state is KeyFieldState.UNREADABLE
    assert fields.room_element.state is KeyFieldState.UNREADABLE


def test_element_mark_fills_the_room_slot_when_no_room_is_named() -> None:
    fields = stamp_key_fields((_tok("элемент В2.1", 0.20),))
    assert fields.room_element.state is KeyFieldState.FOUND
    assert fields.room_element.value == "В2.1"
    assert fields.cipher.state is KeyFieldState.ABSENT


def test_second_reading_keeps_a_field_only_when_both_texts_match() -> None:
    tokens = (
        _tok("шифр: 12345-PZ", 0.05),
        _tok("изм. 3", 0.28),
        _tok("лист 2", 0.46),
        _tok("стадия ПД", 0.64),
        _tok("пом. 267", 0.80),
    )
    same = (
        "шифр: 12345-PZ изм. 3 лист 2 стадия ПД пом. 267"
    )
    agreed = stamp_key_fields(tokens, second_text=same)
    assert _states(agreed) == (KeyFieldState.FOUND,) * 5
    disagreed = stamp_key_fields(
        tokens,
        second_text="шифр: 12345-PZ изм. 4 лист 2 стадия РД пом. 270",
    )
    assert disagreed.cipher.state is KeyFieldState.FOUND
    assert disagreed.revision.state is KeyFieldState.UNREADABLE
    assert disagreed.sheet.state is KeyFieldState.FOUND
    assert disagreed.stage.state is KeyFieldState.UNREADABLE
    assert disagreed.room_element.state is KeyFieldState.UNREADABLE


def test_empty_second_reading_does_not_open_a_dispute() -> None:
    fields = stamp_key_fields((_tok("лист 2", 0.40),), second_text="   ")
    assert fields.sheet.state is KeyFieldState.FOUND
    assert fields.sheet.value == "2"


def test_raster_disagreement_makes_every_field_unreadable() -> None:
    fields = stamp_key_fields(
        (_tok("шифр: 12345-PZ", 0.08), _tok("лист 2", 0.40)),
        text_render_agreement=False,
    )
    assert _states(fields) == (KeyFieldState.UNREADABLE,) * 5
