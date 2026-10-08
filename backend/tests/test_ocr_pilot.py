"""Harness OCR-пилота: Речников вне замера, skip без пути, Wilson не из гипотезы 290/300."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from kontur.evaluation.inventory import QuarantineViolation
from kontur.evaluation.metrics import meets_threshold, wilson
from kontur.evaluation.ocr_pilot import (
    OCR_PILOT_ENV,
    OcrPilotLine,
    accuracy_interval,
    character_accuracy_report,
    eligible_for_ca,
    judge_pooled_ocr,
    load_recognition_lines,
    resolve_pilot_path,
    score_crop_bytes,
    tz_character_accuracy_met,
    vertical_geometry,
)


def _line(
    *,
    object_id: str = "OBJ-NOVOSLOBODSKAYA",
    source: str = "PDF_TEXT_LAYER",
    reference: str = "Площадь 12",
    crop: str = "images/lines/a.png",
) -> OcrPilotLine:
    return OcrPilotLine(
        line_id="L1",
        page_id="P1",
        object_id=object_id,
        reference=reference,
        crop_path=crop,
        source_provenance=source,
    )


def test_pilot_path_is_none_without_env() -> None:
    assert resolve_pilot_path({}) is None


def test_pilot_path_refuses_quarantine() -> None:
    with pytest.raises(QuarantineViolation):
        resolve_pilot_path({OCR_PILOT_ENV: "data/quarantine/test_hidden"})


def test_rechnikov_lines_are_not_eligible() -> None:
    assert eligible_for_ca(_line(object_id="OBJ-RECHNIKOV-7-7")) is False


def test_tesseract_self_preannotation_is_not_eligible() -> None:
    assert eligible_for_ca(_line(source="TESSERACT_RUS_ENG_PREANNOTATION")) is False


def test_pdf_text_layer_on_train_object_is_eligible() -> None:
    assert eligible_for_ca(_line()) is True


def test_vertical_and_broken_encoding_become_line_flags(tmp_path: Path) -> None:
    jsonl = tmp_path / "data" / "recognition_lines.jsonl"
    jsonl.parent.mkdir()
    jsonl.write_text(
        json.dumps(
            {
                "line_id": "L1",
                "object_id": "OBJ-NOVOSLOBODSKAYA",
                "text_raw": "ось",
                "crop_path": "a.png",
                "source_provenance": "PDF_TEXT_LAYER",
                "orientation": "ROTATED_OR_VERTICAL",
                "encoding_flags": ["CID_PLACEHOLDER"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = load_recognition_lines(tmp_path)
    assert lines[0].flags == ("VERTICAL", "LOW_QUALITY")


def test_vertical_short_side_is_counted_without_searching_for_an_angle() -> None:
    lines = (
        OcrPilotLine(
            line_id="L1",
            page_id="P1",
            object_id="OBJ-NOVOSLOBODSKAYA",
            reference="12",
            crop_path="a.png",
            source_provenance="PDF_TEXT_LAYER",
            flags=("VERTICAL",),
            bbox_pdf_pt=(838.195, 65.514, 840.647, 69.2),
        ),
    )
    report = vertical_geometry(lines)
    assert report["n"] == 1
    assert report["n_shorter_than_6pt"] == 1
    assert report["rotation_search"] is False


def test_jsonl_without_object_id_is_invalid(tmp_path: Path) -> None:
    jsonl = tmp_path / "data" / "recognition_lines.jsonl"
    jsonl.parent.mkdir()
    jsonl.write_text('{"line_id": "L1", "text_raw": "x", "crop_path": "a.png"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="object_id"):
        load_recognition_lines(tmp_path)


def test_load_from_zip_and_score_skips_hidden(tmp_path: Path) -> None:
    payload = [
        {
            "line_id": "L-open",
            "page_id": "P1",
            "object_id": "OBJ-NOVOSLOBODSKAYA",
            "text_raw": "hello",
            "crop_path": "images/lines/open.png",
            "source_provenance": "PDF_TEXT_LAYER",
        },
        {
            "line_id": "L-hid",
            "page_id": "P2",
            "object_id": "OBJ-RECHNIKOV-7-7",
            "text_raw": "secret",
            "crop_path": "images/lines/hid.png",
            "source_provenance": "PDF_TEXT_LAYER",
        },
    ]
    raw = "\n".join(json.dumps(row, ensure_ascii=False) for row in payload) + "\n"
    zip_path = tmp_path / "pilot.zip"
    with ZipFile(zip_path, "w") as archive:
        archive.writestr("ocr_pilot_300_v0.1/data/recognition_lines.jsonl", raw)
        archive.writestr("ocr_pilot_300_v0.1/images/lines/open.png", b"PNG")
        archive.writestr("ocr_pilot_300_v0.1/images/lines/hid.png", b"PNG")
    lines = load_recognition_lines(zip_path)
    assert {item.object_id for item in lines} == {
        "OBJ-NOVOSLOBODSKAYA",
        "OBJ-RECHNIKOV-7-7",
    }
    pairs = score_crop_bytes(
        lines,
        {"images/lines/open.png": b"PNG", "images/lines/hid.png": b"PNG"},
        lambda _data: "hello",
    )
    assert pairs == (("hello", "hello"),)


def test_few_perfect_lines_do_not_meet_tz_character_accuracy() -> None:
    pairs = [("ab", "ab")] * 10
    interval = accuracy_interval(pairs)
    assert interval.n == 10
    assert interval.point == 1.0
    assert not tz_character_accuracy_met(interval)
    assert not meets_threshold("character_accuracy", wilson(10, 10))


def test_empty_pairs_do_not_meet_threshold() -> None:
    interval = accuracy_interval(())
    assert interval.n == 0
    assert not tz_character_accuracy_met(interval)


def test_pooled_point_on_one_line_does_not_close_gate_i() -> None:
    report = judge_pooled_ocr([("абвгдеёжзи", "абвгдеёжзи")], gold=True)
    assert report["point_meets_threshold"] is True
    assert report["defined"] is True
    assert report["closes_gate_i"] is False
    line_pass = report["line_pass_rate"]
    assert isinstance(line_pass, dict)
    assert line_pass["wilson_lower_meets_threshold"] is False


def test_line_pass_hides_a_long_miss_so_pooled_ca_blocks_the_gate() -> None:
    """990 коротких попаданий и 10 длинных промахов: доля строк высока, микро-CA нет."""

    pairs = [("А", "А")] * 990 + [("Б" * 100, "В" * 100)] * 10
    report = judge_pooled_ocr(pairs, gold=True)
    line_pass = report["line_pass_rate"]
    assert isinstance(line_pass, dict)
    assert line_pass["wilson_lower_meets_threshold"] is True
    assert report["point_meets_threshold"] is False
    assert report["closes_gate_i"] is False


def test_gold_needs_both_the_pooled_point_and_the_line_sample() -> None:
    pairs = [("АБ", "АБ")] * 80
    gold = judge_pooled_ocr(pairs, gold=True)
    silver = judge_pooled_ocr(pairs, gold=False)
    assert gold["point_meets_threshold"] is True
    assert gold["closes_gate_i"] is True
    assert silver["closes_gate_i"] is False
    assert silver["silver_not_gold"] is True


def test_abstain_drops_coverage_and_stamp_is_its_own_slice() -> None:
    report = character_accuracy_report(
        [("АБ", "АБ"), ("ВГ", "")],
        line_flags=[("STAMP",), ("ABSTAIN",)],
    )
    assert report["coverage"] == pytest.approx(0.5)
    by_flag = report["by_flag"]
    assert isinstance(by_flag, dict)
    stamp = by_flag["STAMP"]
    assert isinstance(stamp, dict)
    assert stamp["n_lines"] == 1
    assert stamp["point"] == pytest.approx(1.0)
    assert report["closes_gate_i"] is False


def test_empty_corpus_stays_unmeasured_even_as_gold() -> None:
    report = judge_pooled_ocr((), gold=True)
    assert report["point"] is None
    assert report["defined"] is False
    assert report["closes_gate_i"] is False
