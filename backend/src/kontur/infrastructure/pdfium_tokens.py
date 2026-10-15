"""Векторные токены страницы через pypdfium2.

OCR не вызывается: нет текстового слоя — пустой список токенов и layer_kind
raster. Координаты в user space, нормализация — через PageFrame (ADR-координаты).
Текст вне CropBox в токены не попадает: это не видимая область.
Режим отрисовки invisible и кегль не выше 0,05 pt в токены не входят:
такой слой не виден на листе и не может стать значением.
"""

from __future__ import annotations

import ctypes
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.models import Polygon

ENGINE_NAME = "pdfium-vector"
ENGINE_VERSION = "0.1.0"
# Ниже этого кегля глиф не читается на листе. Порог тот же, что у проверки слоя.
_TINY_FONT_PT = 0.05
# Невидимый объект размером со страницу не должен гасить соседние видимые строки.
# Строка из десятка глифов ещё внутри своего объекта. Лист целиком — нет.
_MAX_HIDDEN_TO_TOKEN_AREA = 64.0


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


def _hidden_text_boxes(page: pdfium.PdfPage) -> tuple[tuple[float, float, float, float], ...]:
    """Боксы текстовых объектов, которые на листе не рисуются."""

    raw = page.raw
    count = int(pdfium_c.FPDFPage_CountObjects(raw))
    boxes: list[tuple[float, float, float, float]] = []
    for index in range(count):
        obj = pdfium_c.FPDFPage_GetObject(raw, index)
        if pdfium_c.FPDFPageObj_GetType(obj) != pdfium_c.FPDF_PAGEOBJ_TEXT:
            continue
        mode = int(pdfium_c.FPDFTextObj_GetTextRenderMode(obj))
        size = ctypes.c_float()
        size_ok = bool(pdfium_c.FPDFTextObj_GetFontSize(obj, ctypes.byref(size)))
        tiny = size_ok and float(size.value) <= _TINY_FONT_PT
        if mode != int(pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE) and not tiny:
            continue
        left, bottom, right, top = (
            ctypes.c_float(),
            ctypes.c_float(),
            ctypes.c_float(),
            ctypes.c_float(),
        )
        if not pdfium_c.FPDFPageObj_GetBounds(
            obj,
            ctypes.byref(left),
            ctypes.byref(bottom),
            ctypes.byref(right),
            ctypes.byref(top),
        ):
            continue
        boxes.append((float(left.value), float(bottom.value), float(right.value), float(top.value)))
    return tuple(boxes)


def _box_area(box: tuple[float, float, float, float]) -> float:
    left, bottom, right, top = box
    return max(0.0, right - left) * max(0.0, top - bottom)


def _polygon_box(polygon: Polygon) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def _center_inside(
    polygon: Polygon,
    box: tuple[float, float, float, float],
) -> bool:
    left, bottom, right, top = _polygon_box(polygon)
    cx = (left + right) / 2
    cy = (bottom + top) / 2
    box_left, box_bottom, box_right, box_top = box
    return box_left <= cx <= box_right and box_bottom <= cy <= box_top


def _hidden_suppresses(polygon: Polygon, box: tuple[float, float, float, float]) -> bool:
    """Центр строки внутри невидимого объекта, и объект не накрывает весь лист."""

    if not _center_inside(polygon, box):
        return False
    token_area = _box_area(_polygon_box(polygon))
    if token_area <= 1e-6:
        return False
    return _box_area(box) <= token_area * _MAX_HIDDEN_TO_TOKEN_AREA


def _text_without_hidden(
    textpage: pdfium.PdfTextPage,
    rect: tuple[float, float, float, float],
    hidden_boxes: tuple[tuple[float, float, float, float], ...],
    used: set[int],
) -> tuple[str, Polygon] | None:
    """Видимые символы прямоугольника. Каждый символ попадает в один токен."""

    left, bottom, right, top = rect
    parts: list[str] = []
    kept: list[tuple[float, float, float, float]] = []
    claimed: list[int] = []
    for index in range(int(textpage.count_chars())):
        if index in used:
            continue
        raw_box = textpage.get_charbox(index)
        box = tuple(float(value) for value in raw_box)
        if len(box) != 4:
            continue
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        if cx < left or cx > right or cy < bottom or cy > top:
            continue
        claimed.append(index)
        if any(_hidden_suppresses(_quad(*box), hidden) for hidden in hidden_boxes):
            continue
        parts.append(str(textpage.get_text_range(index, 1) or ""))
        kept.append((box[0], box[1], box[2], box[3]))
    used.update(claimed)
    text = "".join(parts).replace("\x00", "").strip()
    if not text or not kept:
        return None
    return text, _quad(
        min(item[0] for item in kept),
        min(item[1] for item in kept),
        max(item[2] for item in kept),
        max(item[3] for item in kept),
    )


def _iter_rects(textpage: pdfium.PdfTextPage) -> Iterator[tuple[str, Polygon]]:
    count = int(textpage.count_rects())
    for index in range(count):
        left, bottom, right, top = textpage.get_rect(index)
        raw = textpage.get_text_bounded(left, bottom, right, top)
        text = str(raw or "").replace("\x00", "").strip()
        if not text:
            continue
        yield text, _quad(float(left), float(bottom), float(right), float(top))


def extract_pdf_bytes(data: bytes, *, max_pages: int | None = None) -> PdfDocumentTokens:
    """Разобрать PDF из памяти. Повреждённый файл — исключение, не пустой успех.

    ``max_pages`` обрезает разбор. ``None`` читает документ целиком.
    """

    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages должен быть положительным")

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
            if max_pages is not None and index >= max_pages:
                break
            media = _box(tuple(page.get_mediabox()))
            crop_raw = page.get_cropbox()
            crop = _box(tuple(crop_raw)) if crop_raw is not None else media
            rotate = int(page.get_rotation())
            frame = PageFrame(media=media, crop=crop, rotate=rotate)
            textpage = page.get_textpage()
            hidden_boxes = _hidden_text_boxes(page)
            try:
                raw_tokens = list(_iter_rects(textpage))
                if hidden_boxes:
                    cleaned: list[tuple[str, Polygon]] = []
                    used: set[int] = set()
                    for _text, polygon in raw_tokens:
                        visible = _text_without_hidden(
                            textpage, _polygon_box(polygon), hidden_boxes, used
                        )
                        if visible is not None:
                            cleaned.append(visible)
                    raw_tokens = cleaned
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
