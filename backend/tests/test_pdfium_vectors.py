"""Сетка векторных штрихов. Не измеряет сечение и не пишет нарушение."""

from __future__ import annotations

import io

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest

from kontur.infrastructure.pdfium_vectors import compare_drawings, drawing_occupancy


def _line_pdf() -> bytes:
    document = pdfium.PdfDocument.new()
    page = document.new_page(200, 200)
    path = pdfium_c.FPDFPageObj_CreateNewPath(20, 40)
    pdfium_c.FPDFPath_LineTo(path, 160, 40)
    pdfium_c.FPDFPath_SetDrawMode(path, 0, 1, 0)
    pdfium_c.FPDFPage_InsertObject(page, path)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def test_textless_line_is_a_stroke() -> None:
    page = drawing_occupancy(_line_pdf(), 1)
    assert page.path_count >= 1
    assert page.occupied


def test_sparse_page_is_not_a_drawing_comparison() -> None:
    left = drawing_occupancy(_line_pdf(), 1)
    right = drawing_occupancy(_line_pdf(), 1)
    result = compare_drawings(left, right, min_paths=40)
    assert result.comparable is False
    assert result.jaccard is None


def test_same_dense_grid_agrees() -> None:
    page = drawing_occupancy(_line_pdf(), 1)
    dense = page.__class__(
        page=1,
        path_count=50,
        occupied=frozenset({(1, 1), (2, 2)}),
    )
    result = compare_drawings(dense, dense)
    assert result.comparable is True
    assert result.jaccard == 1.0


def test_missing_page_is_an_error() -> None:
    with pytest.raises(ValueError):
        drawing_occupancy(_line_pdf(), 3)
