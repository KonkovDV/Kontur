"""Тесты OCR-верификатора (Gate I). Tesseract не требуется для большинства тестов."""

from __future__ import annotations

import math

import pytest

from kontur.infrastructure.ocr_verifier import (
    RasterRegionResult,
    character_accuracy,
    wilson_lower,
)


# ── character_accuracy ────────────────────────────────────────────────────────────────


def test_ca_identical_strings() -> None:
    assert character_accuracy("hello", "hello") == 1.0


def test_ca_completely_different() -> None:
    ca = character_accuracy("aaaa", "bbbb")
    assert ca == 0.0


def test_ca_one_char_off() -> None:
    # "hello" vs "helo": 1 deletion, ref len=4 → 1 - 1/4 = 0.75
    ca = character_accuracy("hello", "helo")
    assert abs(ca - 0.75) < 1e-9


def test_ca_empty_reference_empty_prediction() -> None:
    assert character_accuracy("", "") == 1.0


def test_ca_empty_reference_nonempty_prediction() -> None:
    assert character_accuracy("abc", "") == 0.0


def test_ca_at_threshold_0_95() -> None:
    # 20 символов, 1 ошибка → CA = 0.95
    ref = "a" * 20
    pred = "a" * 19 + "b"
    ca = character_accuracy(pred, ref)
    assert abs(ca - 0.95) < 1e-9


def test_ca_below_gate_i_threshold() -> None:
    ref = "частота колебаний 300"
    pred = "частота колебаний 3XX"
    ca = character_accuracy(pred, ref)
    assert ca < 0.95


def test_ca_nonnegative() -> None:
    # CA не должна быть отрицательной даже при большом расхождении
    ca = character_accuracy("x" * 100, "y")
    assert ca >= 0.0


def test_ca_symmetry_close() -> None:
    # CA(a,b) и CA(b,a) близки, но не обязаны совпадать (знаменатель разный)
    ca_ab = character_accuracy("abcd", "abc")
    ca_ba = character_accuracy("abc", "abcd")
    assert abs(ca_ab - ca_ba) <= 0.5  # не тождественны, но оба в [0,1]


def test_ca_cyrillic_same() -> None:
    s = "Частота колебания"
    assert character_accuracy(s, s) == 1.0


# ── wilson_lower ─────────────────────────────────────────────────────────────────────


def test_wilson_zero_n() -> None:
    assert wilson_lower(0, 0) == 0.0


def test_wilson_perfect_score_large_n() -> None:
    assert wilson_lower(300, 300) > 0.99


def test_wilson_16_correct_out_of_20_below_gate() -> None:
    # GAP-IOS4-VAL: 16/20 → lower ≈ 0.567 < 0.95
    lower = wilson_lower(16, 20)
    assert lower < 0.80


def test_wilson_all_fail_returns_near_zero() -> None:
    assert wilson_lower(0, 100) < 0.05


def test_wilson_monotone_in_successes() -> None:
    vals = [wilson_lower(k, 100) for k in range(0, 101, 10)]
    assert vals == sorted(vals)


# ── RasterRegionResult ────────────────────────────────────────────────────────────────


def test_raster_region_result_empty() -> None:
    r = RasterRegionResult(tokens=(), page_num=1, coverage=0.0)
    assert r.tokens == ()
    assert r.coverage == 0.0
    assert r.engine == "tesseract-5-region-crop"


def test_raster_region_result_defaults_engine() -> None:
    r = RasterRegionResult(tokens=(), page_num=2, coverage=0.5)
    assert "tesseract" in r.engine


# ── интеграция с пайплайном ────────────────────────────────────────────────────────


def test_pipeline_raster_pdf_no_ocr_violation() -> None:
    """Raster PDF без Tesseract → пустые токены → статусы качества, не VIOLATION."""
    from test_pdf_tokens import empty_pdf

    from kontur.application.process_pipeline import PipelineFile, run_process_pipeline
    from kontur.application.scenarios import CompletenessMap
    from kontur.domain.models import DocStage
    from kontur.domain.statuses import Completeness, FindingStatus
    from kontur.infrastructure.pdfium_tokens import file_sha256

    data = empty_pdf()
    item = PipelineFile(
        file_id="f-raster",
        file_hash=file_sha256(data),
        filename="scan.pdf",
        doc_stage=DocStage.PD,
    )
    completeness: CompletenessMap = {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    report = run_process_pipeline(
        object_id="obj-raster-gate-i",
        completeness=completeness,
        files=(item,),
        blobs={"f-raster": data},
    )
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        f.finding_status for f in report.findings
    }
    assert report.pages_built == 1


# ── Gate I stop-condition сценарии ─────────────────────────────────────────────────


def test_gate_i_pass_300_pages_zero_errors() -> None:
    """Пилот: 300/300 → wilson_lower > 0.99 → гейт проходит."""
    lower = wilson_lower(300, 300)
    assert lower > 0.99


def test_gate_i_fail_threshold_below_0_95() -> None:
    """Пилот: 270/300 (CA=0.90) → wilson_lower < 0.95 → stop-condition."""
    lower = wilson_lower(270, 300)
    assert lower < 0.95


def test_gate_i_boundary_290_of_300() -> None:
    """Пилот: 290/300 (CA≈0.967) → wilson_lower > 0.95 → гейт проходит."""
    lower = wilson_lower(290, 300)
    assert lower > 0.95


# ── Tesseract-зависимый тест (skip если не установлен) ─────────────────────────────


@pytest.mark.skipif(
    not __import__(
        "kontur.infrastructure.ocr_verifier", fromlist=["tesseract_available"]
    ).tesseract_available(),
    reason="tesseract not installed",
)
def test_raster_pdf_produces_result_when_tesseract_present() -> None:
    """Raster PDF + Tesseract → ocr_page_bytes возвращает RasterRegionResult без ошибок."""
    from pdf_fixtures import stamp_pdf

    from kontur.infrastructure.ocr_verifier import ocr_page_bytes

    pdf = stamp_pdf("5000")
    result = ocr_page_bytes(pdf, page_num=1)
    assert isinstance(result, RasterRegionResult)
    assert result.page_num == 1
