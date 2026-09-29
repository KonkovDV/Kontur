"""Одна страница PDF в PNG. Полный лист или прямоугольник bbox в [0;1]."""

from __future__ import annotations

from functools import partial
from io import BytesIO

import pypdfium2 as pdfium  # type: ignore[import-untyped,unused-ignore]

from kontur.infrastructure.pdf_guard import pdf_parse_timeout_s, run_pdf_parse_sync

RENDER_SCALE = 2.0


class PageRenderError(ValueError):
    """Страница или bbox не подходят для отрисовки."""


def _render(
    data: bytes,
    page_number: int,
    bbox: tuple[float, float, float, float] | None,
) -> bytes:
    pdf = pdfium.PdfDocument(data)
    try:
        count = len(pdf)
        if page_number < 1 or page_number > count:
            raise PageRenderError(f"страница {page_number} вне 1..{count}")
        page = pdf[page_number - 1]
        bitmap = page.render(scale=RENDER_SCALE)
        try:
            image = bitmap.to_pil()
        finally:
            bitmap.close()
        if bbox is not None:
            left, bottom, right, top = bbox
            width, height = image.size
            x0 = max(0, min(width, int(left * width)))
            x1 = max(0, min(width, int(right * width)))
            y0 = max(0, min(height, int((1.0 - top) * height)))
            y1 = max(0, min(height, int((1.0 - bottom) * height)))
            if x1 <= x0 or y1 <= y0:
                raise PageRenderError("bbox пустой")
            image = image.crop((x0, y0, x1, y1))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """Четыре числа: лево, низ, право, верх, каждое в [0;1]."""

    if raw is None or not raw.strip():
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise PageRenderError("bbox — четыре числа через запятую")
    try:
        values = tuple(float(part.strip()) for part in parts)
    except ValueError as exc:
        raise PageRenderError("bbox содержит не число") from exc
    if len(values) != 4:
        raise PageRenderError("bbox — четыре числа через запятую")
    left, bottom, right, top = values
    if min(values) < 0 or max(values) > 1:
        raise PageRenderError("bbox вне [0;1]")
    if right <= left or top <= bottom:
        raise PageRenderError("bbox пустой")
    return left, bottom, right, top


def render_page_png(
    data: bytes,
    page_number: int,
    bbox: tuple[float, float, float, float] | None = None,
) -> bytes:
    """PNG одной страницы. Номер страницы с 1. bbox — лево, низ, право, верх."""

    parser = partial(_render, page_number=page_number, bbox=bbox)
    return run_pdf_parse_sync(parser, data, timeout_s=pdf_parse_timeout_s())
