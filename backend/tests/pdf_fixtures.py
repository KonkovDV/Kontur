"""Минимальные PDF-фикстуры для pypdfium2. Кириллица не встраивается."""

from __future__ import annotations

import ctypes
import io

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c


def wchar(text: str) -> ctypes.Array[ctypes.c_ushort]:
    raw = (text + "\x00").encode("utf-16-le")
    return (ctypes.c_ushort * (len(raw) // 2)).from_buffer_copy(raw)


def stamp_pdf(
    text: str = "CODE 12345-PZ",
    *,
    fill: tuple[int, int, int, int] = (0, 0, 0, 255),
    width: float = 200.0,
    height: float = 200.0,
    x: float = 20.0,
    y: float = 80.0,
) -> bytes:
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(width, height)
    obj = pdfium_c.FPDFPageObj_NewTextObj(pdf, b"Helvetica", 16)
    pdfium_c.FPDFText_SetText(obj, wchar(text))
    pdfium_c.FPDFPageObj_SetFillColor(obj, *fill)
    pdfium_c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
    pdfium_c.FPDFPage_InsertObject(page, obj)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()
