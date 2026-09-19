"""Gate C: паспорт L1. Пустые ключевые поля не выдумываются."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from kontur.application.extractors.number import PageToken
from kontur.application.passport import KEY_FIELDS, read_passport
from kontur.domain.models import ApprovalStatus, DocStage

HASH = "a" * 64
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "document_passport.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _tok(text: str, x: float, y: float, *, page: int = 1) -> PageToken:
    width, height = 0.18, 0.04
    polygon = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return PageToken(text=text, page=page, polygon_source=polygon, polygon_norm=polygon)


def _read(*tokens: PageToken, filename: str | None = None, layer: str = "vector"):
    return read_passport(
        tokens,
        file_id="file-pd",
        file_hash=HASH,
        filename=filename,
        pages=1,
        layer_kind=layer,
    )


def test_stamp_fills_key_fields_and_matches_schema() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82),
        _tok("изм. 3", 0.32, 0.82),
        _tok("лист 2", 0.50, 0.82),
        _tok("стадия ПД", 0.08, 0.88),
        _tok("утв. 16.09.2026", 0.32, 0.88),
    )
    assert passport.document_code == "12345-PZ"
    assert passport.revision == "3"
    assert passport.sheet == "2"
    assert passport.doc_stage is DocStage.PD
    assert passport.approval_status is ApprovalStatus.APPROVED
    assert str(passport.approval_date) == "2026-09-16"
    assert passport.needs_clarification is False
    assert passport.text_render_agreement is None
    assert passport.extraction_confidence == pytest.approx(1.0)
    jsonschema.Draft202012Validator(SCHEMA).validate(passport.to_schema())


def test_filename_is_not_used_as_document_code() -> None:
    passport = _read(_tok("лист 1", 0.08, 0.82), filename="12345-PZ_RD.pdf")
    assert passport.document_code is None
    assert passport.needs_clarification is True
    assert passport.clarification_reason is not None
    assert "шифр" in passport.clarification_reason


def test_stamp_and_filename_stage_conflict_clears_stage() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82),
        _tok("стадия ПД", 0.40, 0.82),
        filename="RD_12345-PZ.pdf",
    )
    assert passport.document_code == "12345-PZ"
    assert passport.doc_stage is None
    assert passport.needs_clarification is True
    assert passport.to_schema()["doc_stage"] == "UNKNOWN"


def test_filename_stage_used_only_when_stamp_is_silent() -> None:
    passport = _read(_tok("шифр: 12345-PZ", 0.08, 0.82), filename="RD_12345.pdf")
    assert passport.doc_stage is DocStage.RD


def test_unsigned_podp_does_not_mean_approved() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82),
        _tok("подп. Иванов 01.02.2026", 0.40, 0.82),
    )
    assert passport.approval_status is ApprovalStatus.UNKNOWN


def test_empty_utverdil_header_is_not_approved() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82),
        _tok("Утвердил", 0.08, 0.90),
        _tok("Согласовано", 0.08, 0.94),
    )
    assert passport.approval_status is ApprovalStatus.UNKNOWN


def test_filled_utverdil_on_later_sheet_is_approved() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82, page=1),
        _tok("Утвердил", 0.08, 0.92, page=6),
        _tok("Сердюков Р.С.", 0.22, 0.92, page=6),
        _tok("08.04.2024", 0.40, 0.92, page=6),
    )
    assert passport.approval_status is ApprovalStatus.APPROVED
    assert str(passport.approval_date) == "2024-04-08"
    assert passport.document_code == "12345-PZ"


def test_soglasovano_header_on_later_sheet_is_not_approved() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82, page=1),
        _tok("Согласовано", 0.02, 0.90, page=2),
        _tok("ГИП", 0.08, 0.92, page=2),
        _tok("Сердюков", 0.22, 0.92, page=2),
    )
    assert passport.approval_status is ApprovalStatus.UNKNOWN


def test_not_approved_beats_approved_token() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82),
        _tok("не утв", 0.40, 0.82),
        _tok("утв. 01.02.2026", 0.60, 0.82),
    )
    assert passport.approval_status is ApprovalStatus.NOT_APPROVED


def test_empty_vector_page_is_raster_not_ocr() -> None:
    passport = _read(layer="vector")
    assert passport.layer_kind == "raster"
    assert passport.has_embedded_text is False
    assert passport.document_code is None
    assert passport.extraction_confidence is None
    jsonschema.Draft202012Validator(SCHEMA).validate(passport.to_schema())


def test_code_on_title_block_only_not_taken_from_header() -> None:
    passport = _read(
        _tok("шифр: 99999-AR", 0.08, 0.10),
        _tok("лист 4", 0.08, 0.82),
    )
    assert passport.document_code is None
    assert passport.sheet == "4"
    assert passport.needs_clarification is True


def test_second_page_tokens_do_not_replace_first_page_stamp() -> None:
    passport = _read(
        _tok("шифр: 12345-PZ", 0.08, 0.82, page=1),
        _tok("шифр: 00000-XX", 0.08, 0.82, page=2),
    )
    assert passport.document_code == "12345-PZ"


def test_uppercase_hash_is_rejected() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        read_passport((), file_id="f", file_hash="A" * 64)


def test_key_fields_tuple_is_the_exact_match_contract() -> None:
    assert KEY_FIELDS == ("document_code", "revision", "sheet")
