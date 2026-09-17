"""Векторные токены страницы через pypdfium2.

OCR не вызывается: нет текстового слоя — пустой список токенов и layer_kind
raster. Координаты в user space, нормализация — через PageFrame (ADR-координаты).
Текст вне CropBox в токены не попадает: это не видимая область.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.models import Polygon

ENGINE_NAME = "pdfium-vector"
ENGINE_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class PdfPageTokens:
    page: int
    frame: PageFrame
    tokens: tuple[PageToken, ...]
    has_embedded_text: bool
    layer_kind: str


@dataclass(frozen=True, slots=True)
class PdfDocumentTokens:
    file_hash: str
    pages: tuple[PdfPageTokens, ...]

    @property
    def layer_kind(self) -> str:
        kinds = {page.layer_kind for page in self.pages}
        if kinds == {"vector"}:
            return "vector"
        if kinds == {"raster"}:
            return "raster"
        return "hybrid"


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def flatten_tokens(document: PdfDocumentTokens) -> tuple[PageToken, ...]:
    return tuple(token for page in document.pages for token in page.tokens)


def _box(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    left, bottom, right, top = values
    return (float(left), float(bottom), float(right), float(top))


def _quad(left: float, bottom: float, right: float, top: float) -> Polygon:
    return ((left, bottom), (right, bottom), (right, top), (left, top))


def _iter_rects(textpage: pdfium.PdfTextPage) -> Iterator[tuple[str, Polygon]]:
    count = int(textpage.count_rects())
    for index in range(count):
        left, bottom, right, top = textpage.get_rect(index)
        raw = textpage.get_text_bounded(left, bottom, right, top)
        text = str(raw or "").replace("\x00", "").strip()
        if not text:
            continue
        yield text, _quad(float(left), float(bottom), float(right), float(top))


def extract_pdf_bytes(data: bytes) -> PdfDocumentTokens:
    """Разобрать PDF из памяти. Повреждённый файл — исключение, не пустой успех."""

    if not data:
        raise ValueError("PDF не разбирается: пустой файл")
    digest = file_sha256(data)
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise ValueError("PDF не разбирается: повреждён или это не PDF") from exc
    try:
        pages: list[PdfPageTokens] = []
        for index, page in enumerate(document):
            media = _box(tuple(page.get_mediabox()))
            crop_raw = page.get_cropbox()
            crop = _box(tuple(crop_raw)) if crop_raw is not None else media
            rotate = int(page.get_rotation())
            frame = PageFrame(media=media, crop=crop, rotate=rotate)
            textpage = page.get_textpage()
            try:
                raw_tokens = list(_iter_rects(textpage))
            finally:
                textpage.close()
            tokens: list[PageToken] = []
            for text, polygon in raw_tokens:
                try:
                    polygon_norm = to_normalized(polygon, frame)
                except ValueError:
                    continue
                tokens.append(
                    PageToken(
                        text=text,
                        page=index + 1,
                        polygon_source=polygon,
                        polygon_norm=polygon_norm,
                    )
                )
            has_text = bool(tokens)
            pages.append(
                PdfPageTokens(
                    page=index + 1,
                    frame=frame,
                    tokens=tuple(tokens),
                    has_embedded_text=has_text,
                    layer_kind="vector" if has_text else "raster",
                )
            )
        if not pages:
            raise ValueError("PDF без страниц")
        return PdfDocumentTokens(file_hash=digest, pages=tuple(pages))
    finally:
        document.close()


def extract_pdf_path(path: Path) -> PdfDocumentTokens:
    return extract_pdf_bytes(path.read_bytes())
