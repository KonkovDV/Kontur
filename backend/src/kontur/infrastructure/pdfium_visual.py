"""Выборка яркости растра pypdfium2 в боксах текстового слоя."""

from __future__ import annotations

from collections.abc import Sequence

import pypdfium2 as pdfium  # type: ignore[import-untyped,unused-ignore]

from kontur.application.extractors.number import PageToken
from kontur.application.visual_text import (
    VisualTextAssessment,
    agree_visual_and_text,
    token_is_visually_present,
)
from kontur.domain.coordinates import PageFrame
from kontur.domain.geometry import bbox_from_polygon
from kontur.infrastructure.pdf_guard import run_pdf_parse_sync
from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes

RENDER_SCALE = 2.0


def _gray_at(raw: bytes, *, stride: int, channels: int, x: int, y: int) -> float:
    index = y * stride + x * channels
    red, green, blue = raw[index], raw[index + 1], raw[index + 2]
    return 0.299 * red + 0.587 * green + 0.114 * blue


def sample_polygon_gray(
    raw: bytes,
    *,
    width: int,
    height: int,
    stride: int,
    channels: int,
    frame: PageFrame,
    polygon: Sequence[tuple[float, float]],
    scale: float = RENDER_SCALE,
) -> tuple[float, ...]:
    """Пиксели bbox полигона. PDF Y вверх, растр Y вниз, от CropBox."""

    left, bottom, right, top = bbox_from_polygon(tuple(polygon))
    crop_l, crop_b, crop_r, crop_t = frame.crop
    x0 = int((left - crop_l) * scale)
    x1 = int((right - crop_l) * scale)
    y0 = int((crop_t - top) * scale)
    y1 = int((crop_t - bottom) * scale)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    x0 = max(0, min(width - 1, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height - 1, y0))
    y1 = max(0, min(height, y1))
    samples: list[float] = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            samples.append(_gray_at(raw, stride=stride, channels=channels, x=x, y=y))
    return tuple(samples)


def _page_flags(
    page: pdfium.PdfPage,
    tokens: Sequence[PageToken],
    frame: PageFrame,
) -> list[bool | None]:
    bitmap = page.render(scale=RENDER_SCALE)
    try:
        raw = bytes(bitmap.buffer)
        flags: list[bool | None] = []
        for token in tokens:
            if not token.text.strip():
                continue
            samples = sample_polygon_gray(
                raw,
                width=int(bitmap.width),
                height=int(bitmap.height),
                stride=int(bitmap.stride),
                channels=int(bitmap.n_channels),
                frame=frame,
                polygon=token.polygon_source,
            )
            flags.append(token_is_visually_present(token.text, samples))
        return flags
    finally:
        bitmap.close()


def assess_pdf_bytes(data: bytes) -> VisualTextAssessment:
    """Сверить токены текстового слоя с растром той же страницы."""

    return run_pdf_parse_sync(_assess_pdf_bytes, data)


def _assess_pdf_bytes(data: bytes) -> VisualTextAssessment:
    extracted = extract_pdf_bytes(data)
    document = pdfium.PdfDocument(data)
    try:
        flags: list[bool | None] = []
        for page_index, page_tokens in enumerate(extracted.pages):
            page = document[page_index]
            flags.extend(_page_flags(page, page_tokens.tokens, page_tokens.frame))
        return agree_visual_and_text(flags)
    finally:
        document.close()
