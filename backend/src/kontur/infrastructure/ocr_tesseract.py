"""Tesseract: пустой растр и region-crop. Не закрывает гейт I.

Бинарник на PATH ≠ `ocr_text=AVAILABLE`. CA на пилоте — SILVER, не GOLD;
Речников из пилота в замер не входит. Dual-read vector↔OCR в `evaluate_rule`
зовёт `ocr_region_crop`; пустой кроп не считается disagreement.

Ошибка, таймаут, поворот ≠ 0, нет pytesseract — исходные токены без
исключения. Пустой результат — статусы качества, не violation.
Растр для Tesseract — 300 dpi (scale = 300/72 относительно PDF user space).
"""

from __future__ import annotations

import functools
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from importlib import import_module
from io import BytesIO
from pathlib import Path

from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.geometry import bbox_from_polygon
from kontur.domain.models import ExtractionEngine, Polygon
from kontur.infrastructure.pdfium_tokens import PdfDocumentTokens, PdfPageTokens

PDF_USER_DPI = 72.0
OCR_RENDER_DPI = 300.0
RENDER_SCALE = OCR_RENDER_DPI / PDF_USER_DPI
MIN_WORD_CONF = 40.0
REGION_PAD_FRAC = 0.15
REGION_PAD_PT = 8.0
_TESSERACT_LANGS = ("rus+eng", "eng")
# PSM 7 на узкой строке часто возвращает пусто. Следующий режим — только тогда.
_PSM_IF_EMPTY: dict[int, tuple[int, ...]] = {7: (13, 6)}
# Ниже этой высоты кроп растягивается до цели. 40 px заданы до замера, не подбором.
_SHORT_LINE_PX = 32
_TARGET_LINE_PX = 40
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_WORD = re.compile(r"\S+")
_WORD_CORE = re.compile(r"^(\W*)(.*?)(\W*)$")
_LATIN_LOOKALIKES = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "a": "а",
        "c": "с",
        "e": "е",
        "o": "о",
        "p": "р",
        "x": "х",
        "y": "у",
    }
)
# Целиком, не побуквенно: A не похожа на И, но Tesseract так читает «ИНН».
_INN_AS_LATIN = frozenset({"AHH", "HHH", "NHH"})

UserRegion = tuple[float, float, float, float]


def _ensure_tesseract_runtime() -> None:
    """Найти бинарник и rus, если оболочка ещё не подхватила пользовательский PATH.

    Не меняет capabilities и не подменяет системный tessdata в CI.
    """

    if shutil.which("tesseract") is None:
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        candidate = Path(program_files) / "Tesseract-OCR" / "tesseract.exe"
        if candidate.is_file():
            os.environ["PATH"] = str(candidate.parent) + os.pathsep + os.environ.get("PATH", "")
    if os.environ.get("TESSDATA_PREFIX"):
        return
    local_app = os.environ.get("LOCALAPPDATA", "")
    if not local_app:
        return
    local = Path(local_app) / "kontur" / "tessdata"
    if (local / "rus.traineddata").is_file() and (local / "eng.traineddata").is_file():
        os.environ["TESSDATA_PREFIX"] = str(local)


@functools.lru_cache(maxsize=1)
def tesseract_available() -> bool:
    """PATH + импорт pytesseract. Не прогон пилота и не capabilities."""

    _ensure_tesseract_runtime()
    if shutil.which("tesseract") is None:
        return False
    try:
        import_module("pytesseract")
    except ImportError:
        return False
    return True


def _pdfium() -> object:
    return import_module("pypdfium2")


def _open_pdf(data: bytes) -> object | None:
    try:
        engine = _pdfium()
    except ImportError:
        return None
    ctor = getattr(engine, "PdfDocument", None)
    if ctor is None:
        return None
    try:
        opened: object = ctor(data)
    except Exception:
        return None
    return opened


def raster_pages_need_ocr(document: PdfDocumentTokens) -> bool:
    """Пустой растр с rotate=0. Поворот — GAP-OCR-ROT, не тихий bbox."""

    return any(
        page.layer_kind == "raster" and not page.tokens and page.frame.rotate == 0
        for page in document.pages
    )


def expand_user_region(polygon: Polygon, frame: PageFrame) -> UserRegion | None:
    """Расширить bbox значения в user space, клип к CropBox. Вырожденный — None."""

    x0, y0, x1, y1 = bbox_from_polygon(polygon)
    pad_x = max(REGION_PAD_PT, (x1 - x0) * REGION_PAD_FRAC)
    pad_y = max(REGION_PAD_PT, (y1 - y0) * REGION_PAD_FRAC)
    crop_left, crop_bottom, crop_right, crop_top = frame.crop
    left = max(crop_left, x0 - pad_x)
    bottom = max(crop_bottom, y0 - pad_y)
    right = min(crop_right, x1 + pad_x)
    top = min(crop_top, y1 + pad_y)
    if right <= left or top <= bottom:
        return None
    return (left, bottom, right, top)


def _has_cyrillic(text: str) -> bool:
    return _CYRILLIC.search(text) is not None


def _fold_word(word: str) -> str:
    match = _WORD_CORE.match(word)
    if match is None:
        return word
    prefix, core, suffix = match.group(1), match.group(2), match.group(3)
    if core.upper() in _INN_AS_LATIN and core.isascii():
        return f"{prefix}ИНН{suffix}"
    return f"{prefix}{core.translate(_LATIN_LOOKALIKES)}{suffix}"


def fold_latin_lookalikes(text: str) -> str:
    """Латинские двойники → кириллица, если слово или сосед уже русские.

    Слово из одной латиницы без русского соседа не трогается: шифр, ID, ГОСТ.
    Цифры не входят в таблицу замены.
    """

    words = list(_WORD.finditer(text))
    if not words:
        return text
    chars = list(text)
    for index, match in enumerate(words):
        word = match.group()
        prev_cyr = index > 0 and _has_cyrillic(words[index - 1].group())
        next_cyr = index + 1 < len(words) and _has_cyrillic(words[index + 1].group())
        if not _has_cyrillic(word) and not prev_cyr and not next_cyr:
            continue
        folded = _fold_word(word)
        chars[match.start() : match.end()] = list(folded)
    return "".join(chars)


def fold_token_texts(texts: Sequence[str]) -> tuple[str, ...]:
    """Та же замена по соседним токенам. Пробел внутри токена не ожидается."""

    folded = fold_latin_lookalikes(" ".join(texts)).split(" ")
    if len(folded) != len(texts):
        return tuple(texts)
    return tuple(folded)


def tokens_from_tesseract_payload(
    payload: Mapping[str, Sequence[object]],
    page: PdfPageTokens,
    image_size: tuple[int, int],
    *,
    region: UserRegion | None = None,
) -> tuple[PageToken, ...]:
    """Слова Tesseract → grounded PageToken.

    Без region bitmap = CropBox при rotate=0. С region — кадр кропа в user space.
    conf < MIN_WORD_CONF и выход за [0;1] отбрасываются.
    """

    img_w, img_h = image_size
    if img_w <= 0 or img_h <= 0:
        return ()
    texts = payload.get("text")
    if texts is None:
        return ()
    box_left, box_bottom, box_right, box_top = region if region is not None else page.frame.crop
    box_w = box_right - box_left
    box_h = box_top - box_bottom
    if box_w <= 0 or box_h <= 0:
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
        x0 = box_left + (left / img_w) * box_w
        x1 = box_left + ((left + width) / img_w) * box_w
        y1 = box_top - (top / img_h) * box_h
        y0 = box_top - ((top + height) / img_h) * box_h
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
    if not out:
        return ()
    folded = fold_token_texts([token.text for token in out])
    return tuple(replace(token, text=text) for token, text in zip(out, folded, strict=True))


class PageImageCache:
    """PIL-кадры страниц при 300 dpi. Не сериализуется, не доказательство."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._images: dict[int, object] = {}

    def page_image(self, page_number: int) -> object | None:
        cached = self._images.get(page_number)
        if cached is not None:
            return cached
        pdf = _open_pdf(self._data)
        if pdf is None:
            return None
        try:
            length = len(pdf)  # type: ignore[arg-type]
            if page_number < 1 or page_number > length:
                return None
            image = _render_pil(pdf[page_number - 1])  # type: ignore[index]
        except (OSError, RuntimeError, ValueError, AttributeError, TypeError):
            return None
        finally:
            close = getattr(pdf, "close", None)
            if close is not None:
                close()
        if image is None:
            return None
        self._images[page_number] = image
        return image


def ocr_region_crop(
    data: bytes,
    *,
    page_number: int,
    frame: PageFrame,
    polygon: Polygon,
    cache: PageImageCache | None = None,
) -> tuple[PageToken, ...]:
    """Tesseract на расширенном кропе значения. Поворот и сбой — пустой кортеж."""

    if not tesseract_available() or frame.rotate != 0:
        return ()
    region = expand_user_region(polygon, frame)
    if region is None:
        return ()
    store = cache if cache is not None else PageImageCache(data)
    image = store.page_image(page_number)
    cropped = _crop_to_region(image, frame, region)
    if cropped is None:
        return ()
    size = _image_size(cropped)
    if size is None:
        return ()
    try:
        pytesseract = import_module("pytesseract")
    except ImportError:
        return ()
    payload = _image_to_data(pytesseract, cropped, psm=6)
    if payload is None:
        return ()
    stub = PdfPageTokens(
        page=page_number,
        frame=frame,
        tokens=(),
        has_embedded_text=False,
        layer_kind="raster",
    )
    return tokens_from_tesseract_payload(payload, stub, size, region=region)


def ocr_image_bytes(data: bytes, *, psm: int = 7) -> str:
    """Текст с готового crop-изображения. Для CA пилота, не для вердикта."""

    if not data or not tesseract_available():
        return ""
    try:
        pytesseract = import_module("pytesseract")
        pillow = import_module("PIL.Image")
    except ImportError:
        return ""
    open_image = getattr(pillow, "open", None)
    if open_image is None:
        return ""
    try:
        image = open_image(BytesIO(data))
    except (OSError, ValueError):
        return ""
    image = _upscale_short_crop(image)
    tess_error = getattr(pytesseract, "TesseractError", RuntimeError)
    to_string = getattr(pytesseract, "image_to_string", None)
    if to_string is None:
        return ""
    for current in (psm, *_PSM_IF_EMPTY.get(psm, ())):
        for lang in _TESSERACT_LANGS:
            try:
                text = to_string(image, lang=lang, config=f"--psm {current}")
            except (tess_error, UnicodeError, OSError):
                continue
            if isinstance(text, str) and text.strip():
                return fold_latin_lookalikes(text.strip())
    return ""


def _upscale_short_crop(image: object) -> object:
    """Строка ниже 32 px → высота 40. Без бинаризации."""

    size = _image_size(image)
    if size is None:
        return image
    width, height = size
    if height <= 0 or height >= _SHORT_LINE_PX:
        return image
    resize = getattr(image, "resize", None)
    if resize is None:
        return image
    try:
        pillow = import_module("PIL.Image")
    except ImportError:
        return image
    resampling = getattr(getattr(pillow, "Resampling", pillow), "LANCZOS", 1)
    new_width = max(1, int(round(width * _TARGET_LINE_PX / height)))
    try:
        return resize((new_width, _TARGET_LINE_PX), resampling)
    except (TypeError, ValueError):
        return image


def _ocr_job(data: bytes, page: PdfPageTokens) -> tuple[PageToken, ...]:
    """OCR одной страницы в воркере. Документ открывается здесь, не через pickle."""

    pdf = _open_pdf(data)
    if pdf is None:
        return ()
    try:
        return _ocr_pdf_page(pdf[page.page - 1], page)  # type: ignore[index]
    finally:
        close = getattr(pdf, "close", None)
        if close is not None:
            close()


def _needs_ocr(page: PdfPageTokens) -> bool:
    return page.layer_kind == "raster" and not page.tokens and page.frame.rotate == 0


def fill_empty_raster_pages(document: PdfDocumentTokens, data: bytes) -> PdfDocumentTokens:
    """Заполнить пустые raster-страницы. Векторные токены не трогает.

    Две и больше пустых страниц читаются пулом процессов, не больше 16.
    Одна страница остаётся в этом процессе.
    """

    if not tesseract_available() or not raster_pages_need_ocr(document):
        return document
    targets = [page for page in document.pages if _needs_ocr(page)]
    filled: dict[int, tuple[PageToken, ...]] = {}
    if len(targets) >= 2:
        workers = min(os.cpu_count() or 1, 16)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_ocr_job, data, page): page.page for page in targets}
            for future, number in futures.items():
                try:
                    filled[number] = future.result()
                except (OSError, RuntimeError, ValueError, AttributeError, TypeError):
                    filled[number] = ()
    else:
        pdf = _open_pdf(data)
        if pdf is None:
            return document
        try:
            for page in targets:
                try:
                    filled[page.page] = _ocr_pdf_page(pdf[page.page - 1], page)  # type: ignore[index]
                except (OSError, RuntimeError, ValueError, AttributeError, TypeError):
                    filled[page.page] = ()
        finally:
            close = getattr(pdf, "close", None)
            if close is not None:
                close()
    pages: list[PdfPageTokens] = []
    for page in document.pages:
        tokens = filled.get(page.page)
        if tokens:
            pages.append(replace(page, tokens=tokens))
        else:
            pages.append(page)
    return PdfDocumentTokens(file_hash=document.file_hash, pages=tuple(pages))


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


def _render_pil(pdf_page: object) -> object | None:
    render = getattr(pdf_page, "render", None)
    if render is None:
        return None
    bitmap = render(scale=RENDER_SCALE)
    try:
        to_pil = getattr(bitmap, "to_pil", None)
        if to_pil is None:
            return None
        rendered: object = to_pil()
        return rendered
    finally:
        close = getattr(bitmap, "close", None)
        if close is not None:
            close()


def _crop_to_region(image: object | None, frame: PageFrame, region: UserRegion) -> object | None:
    if image is None:
        return None
    size = _image_size(image)
    if size is None:
        return None
    img_w, img_h = size
    crop_left, crop_bottom, crop_right, crop_top = frame.crop
    crop_w = crop_right - crop_left
    crop_h = crop_top - crop_bottom
    if crop_w <= 0 or crop_h <= 0:
        return None
    left, bottom, right, top = region
    px0 = int(round((left - crop_left) / crop_w * img_w))
    px1 = int(round((right - crop_left) / crop_w * img_w))
    py0 = int(round((crop_top - top) / crop_h * img_h))
    py1 = int(round((crop_top - bottom) / crop_h * img_h))
    px0 = max(0, min(img_w - 1, px0))
    px1 = max(px0 + 1, min(img_w, px1))
    py0 = max(0, min(img_h - 1, py0))
    py1 = max(py0 + 1, min(img_h, py1))
    crop = getattr(image, "crop", None)
    if crop is None:
        return None
    try:
        cropped: object = crop((px0, py0, px1, py1))
    except (TypeError, ValueError):
        return None
    return cropped


def _ocr_pdf_page(pdf_page: object, page: PdfPageTokens) -> tuple[PageToken, ...]:
    try:
        pytesseract = import_module("pytesseract")
    except ImportError:
        return ()
    image = _render_pil(pdf_page)
    size = _image_size(image)
    if image is None or size is None:
        return ()
    payload = _image_to_data(pytesseract, image, psm=6)
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


def _image_to_data(
    pytesseract: object,
    image: object,
    *,
    psm: int,
) -> dict[str, list[object]] | None:
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
                config=f"--psm {psm}",
                output_type=dict_type,
            )
        except (tess_error, UnicodeError, OSError):
            continue
        if isinstance(payload, dict) and payload.get("text"):
            return payload
    return None
