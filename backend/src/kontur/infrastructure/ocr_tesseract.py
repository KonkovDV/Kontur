"""Tesseract на пустых raster-страницах. Не закрывает гейт I.

Бинарник на PATH ≠ `ocr_text=AVAILABLE`: Character Accuracy на пилоте
`ocr_pilot_20260811` не измерена, dual-read vector↔OCR не стоит в
`evaluate_rule`, полный кадр страницы — не region-crop ×3 из bake-off.

Ошибка, таймаут, поворот ≠ 0, нет pytesseract — исходные токены без
исключения. Пустой результат — статусы качества, не violation.
"""

from __future__ import annotations

import functools
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from importlib import import_module

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import to_normalized
from kontur.domain.models import ExtractionEngine, Polygon
from kontur.infrastructure.pdfium_tokens import PdfDocumentTokens, PdfPageTokens

RENDER_SCALE = 3.0
MIN_WORD_CONF = 40.0
_TESSERACT_LANGS = ("rus+eng", "eng")


@functools.lru_cache(maxsize=1)
def tesseract_available() -> bool:
    """PATH + импорт pytesseract. Не прогон пилота и не capabilities."""

    if shutil.which("tesseract") is None:
        return False
    try:
        import_module("pytesseract")
    except ImportError:
        return False
    return True


def raster_pages_need_ocr(document: PdfDocumentTokens) -> bool:
    """Пустой растр с rotate=0. Поворот — GAP-OCR-ROT, не тихий bbox."""

    return any(
        page.layer_kind == "raster" and not page.tokens and page.frame.rotate == 0
        for page in document.pages
    )


def tokens_from_tesseract_payload(
    payload: Mapping[str, Sequence[object]],
    page: PdfPageTokens,
    image_size: tuple[int, int],
) -> tuple[PageToken, ...]:
    """Слова Tesseract → grounded PageToken в user space CropBox.

    Bitmap считается кадром CropBox при rotate=0. conf < MIN_WORD_CONF
    и выход за [0;1] отбрасываются, не клипуются в нарушение.
    """

    img_w, img_h = image_size
    if img_w <= 0 or img_h <= 0:
        return ()
    texts = payload.get("text")
    if texts is None:
        return ()
    crop_left, crop_bottom, crop_right, crop_top = page.frame.crop
    crop_w = crop_right - crop_left
    crop_h = crop_top - crop_bottom
    if crop_w <= 0 or crop_h <= 0:
        return ()
    out: list[PageToken] = []
    for index, raw_text in enumerate(texts):
        text = str(raw_text or "").replace("\x00", "").strip()
        if not text:
            continue
        if _field_float(payload, "conf", index) < MIN_WORD_CONF:
            continue
        left = _field_float(payload, "left", index)
        top = _field_float(payload, "top", index)
        width = _field_float(payload, "width", index)
        height = _field_float(payload, "height", index)
        if width <= 0 or height <= 0:
            continue
        x0 = crop_left + (left / img_w) * crop_w
        x1 = crop_left + ((left + width) / img_w) * crop_w
        y1 = crop_top - (top / img_h) * crop_h
        y0 = crop_top - ((top + height) / img_h) * crop_h
        polygon: Polygon = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
        try:
            polygon_norm = to_normalized(polygon, page.frame)
        except ValueError:
            continue
        out.append(
            PageToken(
                text=text,
                page=page.page,
                polygon_source=polygon,
                polygon_norm=polygon_norm,
                engine=ExtractionEngine.OCR,
            )
        )
    return tuple(out)


def fill_empty_raster_pages(document: PdfDocumentTokens, data: bytes) -> PdfDocumentTokens:
    """Заполнить пустые raster-страницы. Векторные токены не трогает."""

    if not tesseract_available() or not raster_pages_need_ocr(document):
        return document
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError:
        return document
    try:
        pages: list[PdfPageTokens] = []
        for page in document.pages:
            if page.layer_kind != "raster" or page.tokens or page.frame.rotate != 0:
                pages.append(page)
                continue
            try:
                tokens = _ocr_pdf_page(pdf[page.page - 1], page)
            except (OSError, RuntimeError, ValueError, AttributeError):
                pages.append(page)
                continue
            pages.append(replace(page, tokens=tokens) if tokens else page)
        return PdfDocumentTokens(file_hash=document.file_hash, pages=tuple(pages))
    finally:
        pdf.close()


def _field_float(payload: Mapping[str, Sequence[object]], name: str, index: int) -> float:
    values = payload.get(name)
    if values is None or index >= len(values):
        return -1.0
    raw = values[index]
    if isinstance(raw, bool):
        return -1.0
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return -1.0
    return -1.0


def _ocr_pdf_page(pdf_page: object, page: PdfPageTokens) -> tuple[PageToken, ...]:
    try:
        pytesseract = import_module("pytesseract")
    except ImportError:
        return ()
    render = getattr(pdf_page, "render", None)
    if render is None:
        return ()
    bitmap = render(scale=RENDER_SCALE)
    try:
        to_pil = getattr(bitmap, "to_pil", None)
        if to_pil is None:
            return ()
        image = to_pil()
        size = _image_size(image)
        if size is None:
            return ()
        payload = _image_to_data(pytesseract, image)
    finally:
        close = getattr(bitmap, "close", None)
        if close is not None:
            close()
    if payload is None:
        return ()
    return tokens_from_tesseract_payload(payload, page, size)


def _image_size(image: object) -> tuple[int, int] | None:
    size = getattr(image, "size", None)
    if not isinstance(size, tuple) or len(size) != 2:
        return None
    width, height = size
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    return width, height


def _image_to_data(pytesseract: object, image: object) -> dict[str, list[object]] | None:
    tess_error = getattr(pytesseract, "TesseractError", RuntimeError)
    image_to_data = getattr(pytesseract, "image_to_data", None)
    output = getattr(pytesseract, "Output", None)
    if image_to_data is None or output is None:
        return None
    dict_type = getattr(output, "DICT", "dict")
    for lang in _TESSERACT_LANGS:
        try:
            payload = image_to_data(
                image,
                lang=lang,
                config="--psm 6",
                output_type=dict_type,
            )
        except tess_error:
            continue
        if isinstance(payload, dict) and payload.get("text"):
            return payload
    return None
