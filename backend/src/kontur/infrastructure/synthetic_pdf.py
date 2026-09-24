"""Синтетический векторный PDF с кириллицей. Не документ организатора."""

from __future__ import annotations

import ctypes
import io
import os
from collections.abc import Sequence
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
)


def wchar(text: str) -> ctypes.Array[ctypes.c_ushort]:
    raw = (text + "\x00").encode("utf-16-le")
    return (ctypes.c_ushort * (len(raw) // 2)).from_buffer_copy(raw)


def contest_slice_font() -> Path | None:
    """TTF с кириллицей. None — синтетический лист собрать нельзя."""

    env = os.environ.get("KONTUR_TEST_FONT")
    paths = (Path(env),) + _FONT_CANDIDATES if env else _FONT_CANDIDATES
    for path in paths:
        if path.is_file():
            return path
    return None


def cyrillic_pdf(
    lines: Sequence[tuple[str, float, float]],
    *,
    width: float = 400.0,
    height: float = 300.0,
    size: float = 10.0,
    font_path: Path | None = None,
) -> bytes:
    """Каждая строка — отдельный текстовый объект."""

    source = font_path or contest_slice_font()
    if source is None:
        raise FileNotFoundError("нет TTF с кириллицей: KONTUR_TEST_FONT или системный шрифт")
    font_data = source.read_bytes()
    buf = (ctypes.c_ubyte * len(font_data)).from_buffer_copy(font_data)
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(width, height)
    font = pdfium_c.FPDFText_LoadFont(
        pdf, buf, len(font_data), pdfium_c.FPDF_FONT_TRUETYPE, 1
    )
    if not font:
        pdf.close()
        raise RuntimeError(f"pdfium не загрузил шрифт {source}")
    for text, x, y in lines:
        obj = pdfium_c.FPDFPageObj_CreateTextObj(pdf, font, size)
        pdfium_c.FPDFText_SetText(obj, wchar(text))
        pdfium_c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
        pdfium_c.FPDFPage_InsertObject(page, obj)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()
