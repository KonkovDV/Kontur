"""Масштаб штампа и ширина пары параллельных штрихов."""

from __future__ import annotations

import io

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

from kontur.application.extractors.drawing_scale import scale_denominator
from kontur.application.extractors.number import PageToken
from kontur.infrastructure.duct_geometry import (
    PT_TO_MM,
    Segment,
    gaps_agree,
    pair_parallel,
    segments_on_page,
    width_mm,
)


def _tok(text: str, y: float) -> PageToken:
    polygon = ((0.05, y), (0.25, y), (0.25, y + 0.03), (0.05, y + 0.03))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def test_scale_reads_stamp_and_ignores_drawing() -> None:
    tokens = (_tok("план", 0.40), _tok("М", 0.90), _tok("1:100", 0.90))
    assert scale_denominator(tokens) == 100
    assert scale_denominator((_tok("1:50", 0.40),)) is None


def test_width_uses_paper_millimetres_times_scale() -> None:
    gap = 400 / (PT_TO_MM * 100)
    assert abs(width_mm(gap, 100) - 400) / 400 < 0.01
    pair = pair_parallel(
        [Segment(0, 0, 80, 0), Segment(0, gap, 80, gap)],
        100,
    )
    assert len(pair) == 1
    assert abs(pair[0].width_mm - 400) / 400 < 0.01


def test_skewed_pair_disagrees_and_is_not_averaged() -> None:
    pairs = pair_parallel(
        [Segment(0, 0, 80, 0), Segment(0, 8, 80, 30)],
        100,
        angle_deg=20,
    )
    assert len(pairs) == 1
    assert gaps_agree(pairs[0].gap_pt, pairs[0].reverse_gap_pt, tolerance_rel=0.02) is False


def test_skewed_or_short_lines_are_not_a_duct() -> None:
    assert pair_parallel([Segment(0, 0, 80, 0), Segment(0, 0, 80, 40)], 100) == []
    assert pair_parallel([Segment(0, 0, 10, 0), Segment(0, 8, 10, 8)], 100) == []


def _line_pdf(y0: float, y1: float) -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    for y in (y0, y1):
        path = pdfium_c.FPDFPageObj_CreateNewPath(10, y)
        pdfium_c.FPDFPath_LineTo(path, 120, y)
        pdfium_c.FPDFPath_SetDrawMode(path, 0, 1, 0)
        pdfium_c.FPDFPage_InsertObject(page, path)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def test_pdf_line_pair_becomes_segments() -> None:
    data = _line_pdf(40, 52)
    segments = segments_on_page(data, 1)
    assert len(segments) == 2
    pairs = pair_parallel(segments, 100)
    assert len(pairs) == 1
    assert abs(pairs[0].width_mm - 12 * PT_TO_MM * 100) < 5
