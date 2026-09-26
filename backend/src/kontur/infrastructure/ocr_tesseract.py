"""Tesseract: пустой растр и region-crop. Не закрывает гейт I.

Бинарник на PATH ≠ `ocr_text=AVAILABLE`. CA на пилоте — SILVER, не GOLD;
Речников из пилота в замер не входит. Dual-read vector↔OCR в `evaluate_rule`
зовёт `ocr_region_crop`; пустой кроп не считается disagreement.

Ошибка, таймаут или отсутствие pytesseract оставляют исходные токены.
Поворот кадра не обрывает кроп: pdfium уже отдал видимую страницу.
Цветная печать выбеливается до распознавания; чёрный текст и серый
штамп не трогаются. Пустой результат — статусы качества, не violation.
`ocr_text` остаётся MEASURED. Гейт I этим модулем не закрывается.
eslav и Tesseract читают кроп по отдельности: нет ответа — не голос.
Растр для Tesseract — 300 dpi (scale = 300/72 относительно PDF user space).
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from importlib import import_module
from io import BytesIO
from pathlib import Path

from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame, polygons_from_view_pixels, to_normalized, to_source
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
    """Пустой растр, включая /Rotate. Повторный проход — если прямой OCR пуст."""

    return any(_needs_ocr(page) for page in document.pages)


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
    view_origin: tuple[float, float] | None = None,
    page_image_size: tuple[int, int] | None = None,
) -> tuple[PageToken, ...]:
    """Слова Tesseract → grounded PageToken.

    Без region bitmap = видимый кадр pdfium, включая /Rotate.
    С view_origin слово лежит на кропе этого кадра.
    С region — кадр кропа в user space при rotate=0.
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
        if view_origin is not None and page_image_size is not None:
            origin_x, origin_y = view_origin
            mapped = polygons_from_view_pixels(
                origin_x + left,
                origin_y + top,
                origin_x + left + width,
                origin_y + top + height,
                page_image_size,
                page.frame,
            )
            if mapped is None:
                continue
            polygon, polygon_norm = mapped
        elif region is None:
            mapped = polygons_from_view_pixels(
                left, top, left + width, top + height, image_size, page.frame
            )
            if mapped is None:
                continue
            polygon, polygon_norm = mapped
        else:
            x0 = box_left + (left / img_w) * box_w
            x1 = box_left + ((left + width) / img_w) * box_w
            y1 = box_top - (top / img_h) * box_h
            y0 = box_top - ((top + height) / img_h) * box_h
            polygon = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
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
    """Tesseract на расширенном кропе значения. Сбой и пустой кадр — пустой кортеж."""

    if not tesseract_available():
        return ()
    region = expand_user_region(polygon, frame)
    if region is None:
        return ()
    store = cache if cache is not None else PageImageCache(data)
    image = store.page_image(page_number)
    full_size = _image_size(image)
    box = None if full_size is None else _crop_pixels(frame, region, full_size)
    cropped = _crop_image(image, box)
    if cropped is None or box is None or full_size is None:
        return ()
    cropped = suppress_colored_seal(cropped)
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
    return tokens_from_tesseract_payload(
        payload,
        stub,
        size,
        view_origin=(float(box[0]), float(box[1])),
        page_image_size=full_size,
    )


def ocr_region_eslav(
    data: bytes,
    *,
    page_number: int,
    frame: PageFrame,
    polygon: Polygon,
    cache: PageImageCache | None = None,
) -> tuple[PageToken, ...]:
    """eslav на том же кропе, что и Tesseract. Нет весов — пусто, не ошибка."""

    from kontur.infrastructure.ocr_rapid import rapid_page_tokens, weights_ready

    if not weights_ready():
        return ()
    region = expand_user_region(polygon, frame)
    if region is None:
        return ()
    store = cache if cache is not None else PageImageCache(data)
    image = store.page_image(page_number)
    full_size = _image_size(image)
    box = None if full_size is None else _crop_pixels(frame, region, full_size)
    cropped = _crop_image(image, box)
    if cropped is None:
        return ()
    cropped = suppress_colored_seal(cropped)
    size = _image_size(cropped)
    if size is None:
        return ()
    width, height = size
    stub = PdfPageTokens(
        page=page_number,
        frame=PageFrame(
            media=(0.0, 0.0, float(width), float(height)),
            crop=(0.0, 0.0, float(width), float(height)),
            rotate=0,
        ),
        tokens=(),
        has_embedded_text=False,
        layer_kind="raster",
    )
    rapid = rapid_page_tokens(cropped, stub, size)
    if not rapid:
        return ()
    return rapid


def _bottom_band(image: object | None) -> object | None:
    size = _image_size(image)
    if size is None or image is None:
        return None
    width, height = size
    if height < 8:
        return None
    top = int(height * 0.72)
    crop = getattr(image, "crop", None)
    if crop is None:
        return None
    try:
        band: object = crop((0, top, width, height))
    except (TypeError, ValueError):
        return None
    return band


def stamp_cipher_reads(data: bytes, page_count: int) -> tuple[str, ...]:
    """Шифры нижней полосы последней страницы отдельно от eslav и Tesseract.

    Нет весов eslav — пустой кортеж: векторный шифр не оспаривается.
    Движок без шифра по regex в кортеж не входит.
    """

    from kontur.application.passport import cipher_from_text
    from kontur.infrastructure.ocr_rapid import rapid_page_tokens, weights_ready

    if page_count < 1 or not weights_ready() or not tesseract_available():
        return ()
    band = _bottom_band(PageImageCache(data).page_image(page_count))
    size = _image_size(band)
    if band is None or size is None:
        return ()
    width, height = size
    stub = PdfPageTokens(
        page=page_count,
        frame=PageFrame(
            media=(0.0, 0.0, float(width), float(height)),
            crop=(0.0, 0.0, float(width), float(height)),
            rotate=0,
        ),
        tokens=(),
        has_embedded_text=False,
        layer_kind="raster",
    )
    found: list[str] = []
    rapid = rapid_page_tokens(band, stub, size)
    if rapid:
        code = cipher_from_text(" ".join(item.text for item in rapid))
        if code:
            found.append(code)
    try:
        pytesseract = import_module("pytesseract")
    except ImportError:
        return tuple(found)
    payload = _image_to_data(pytesseract, band, psm=6)
    if payload is None:
        return tuple(found)
    tokens = tokens_from_tesseract_payload(payload, stub, size)
    code = cipher_from_text(" ".join(item.text for item in tokens))
    if code:
        found.append(code)
    return tuple(found)


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
    """OCR одной страницы. Документ открывается здесь, не через pickle."""

    pdf = _open_pdf(data)
    if pdf is None:
        return ()
    try:
        return _ocr_pdf_page(pdf[page.page - 1], page)  # type: ignore[index]
    finally:
        close = getattr(pdf, "close", None)
        if close is not None:
            close()


def _ocr_job_path(path: str, page: PdfPageTokens) -> tuple[PageToken, ...]:
    """Та же страница, но воркер открывает файл сам: в очередь не кладётся весь PDF."""

    return _ocr_job(Path(path).read_bytes(), page)


def _needs_ocr(page: PdfPageTokens) -> bool:
    return page.layer_kind == "raster" and not page.tokens


def _fill_pages_here(
    data: bytes, targets: Sequence[PdfPageTokens]
) -> dict[int, tuple[PageToken, ...]]:
    filled: dict[int, tuple[PageToken, ...]] = {}
    pdf = _open_pdf(data)
    if pdf is None:
        return {page.page: () for page in targets}
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
    return filled


def fill_empty_raster_pages(document: PdfDocumentTokens, data: bytes) -> PdfDocumentTokens:
    """Заполнить пустые raster-страницы. Векторные токены не трогает.

    Две и больше пустых страниц читаются пулом. В очередь уходит путь к
    временному файлу, не байты PDF. Крупный файл — не больше двух воркеров.
    Сломанный пул дочитывается в этом процессе.
    """

    from kontur.infrastructure.ocr_rapid import weights_ready

    if not raster_pages_need_ocr(document):
        return document
    if not tesseract_available() and not weights_ready():
        return document
    targets = [page for page in document.pages if _needs_ocr(page)]
    # На Windows пул внутри дочернего разбора оставляет процессы и даёт WinError 1450.
    if len(targets) < 2 or sys.platform == "win32":
        filled = _fill_pages_here(data, targets)
    else:
        filled = _fill_with_pool(data, targets)
    pages: list[PdfPageTokens] = []
    for page in document.pages:
        tokens = filled.get(page.page)
        if tokens:
            pages.append(replace(page, tokens=tokens))
        else:
            pages.append(page)
    return PdfDocumentTokens(file_hash=document.file_hash, pages=tuple(pages))


def _fill_with_pool(
    data: bytes, targets: Sequence[PdfPageTokens]
) -> dict[int, tuple[PageToken, ...]]:
    workers = min(os.cpu_count() or 1, 16)
    if len(data) > 8_000_000:
        workers = min(workers, 2)
    filled: dict[int, tuple[PageToken, ...]] = {}
    broken = False
    handle = tempfile.NamedTemporaryFile(prefix="kontur-ocr-", suffix=".pdf", delete=False)
    path = handle.name
    try:
        handle.write(data)
        handle.close()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_ocr_job_path, path, page): page.page for page in targets}
            for future, number in futures.items():
                try:
                    filled[number] = future.result()
                except BrokenProcessPool:
                    broken = True
                    break
                except (OSError, RuntimeError, ValueError, AttributeError, TypeError):
                    filled[number] = ()
    except BrokenProcessPool:
        broken = True
    finally:
        Path(path).unlink(missing_ok=True)
    if broken:
        pending = [page for page in targets if page.page not in filled]
        filled.update(_fill_pages_here(data, pending))
    return filled


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


def _crop_pixels(
    frame: PageFrame,
    region: UserRegion,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """User-space кроп → пиксели видимого кадра. /Rotate уже в кадре pdfium."""

    img_w, img_h = image_size
    if img_w <= 0 or img_h <= 0:
        return None
    left, bottom, right, top = region
    polygon = ((left, bottom), (right, bottom), (right, top), (left, top))
    try:
        norm = to_normalized(polygon, frame)
    except ValueError:
        return None
    xs = [point[0] * img_w for point in norm]
    ys = [point[1] * img_h for point in norm]
    px0 = int(round(min(xs)))
    px1 = int(round(max(xs)))
    py0 = int(round(min(ys)))
    py1 = int(round(max(ys)))
    px0 = max(0, min(img_w - 1, px0))
    px1 = max(px0 + 1, min(img_w, px1))
    py0 = max(0, min(img_h - 1, py0))
    py1 = max(py0 + 1, min(img_h, py1))
    return (px0, py0, px1, py1)


def _crop_image(
    image: object | None,
    box: tuple[int, int, int, int] | None,
) -> object | None:
    if image is None or box is None:
        return None
    crop = getattr(image, "crop", None)
    if crop is None:
        return None
    try:
        cropped: object = crop(box)
    except (TypeError, ValueError):
        return None
    return cropped


def _point_band(band: object, table: list[int]) -> object:
    point = getattr(band, "point", None)
    if point is None:
        raise TypeError("канал без point")
    painted: object = point(table)
    return painted


def _ink_mask(chops: object, lead: object, other_a: object, other_b: object) -> object:
    bright = [255 if value > 100 else 0 for value in range(256)]
    gap = [255 if value > 40 else 0 for value in range(256)]
    subtract = getattr(chops, "subtract", None)
    multiply = getattr(chops, "multiply", None)
    if subtract is None or multiply is None:
        raise TypeError("ImageChops без subtract/multiply")
    lead_hi = _point_band(lead, bright)
    gap_a = _point_band(subtract(lead, other_a), gap)
    gap_b = _point_band(subtract(lead, other_b), gap)
    masked: object = multiply(multiply(lead_hi, gap_a), gap_b)
    return masked


def suppress_colored_seal(image: object) -> object:
    """Красная и синяя печать → белый фон. Чёрный текст и серый штамп остаются."""

    try:
        pillow = import_module("PIL.Image")
        chops = import_module("PIL.ImageChops")
    except ImportError:
        return image
    convert = getattr(image, "convert", None)
    size = _image_size(image)
    if convert is None or size is None:
        return image
    rgb = convert("RGB")
    split = getattr(rgb, "split", None)
    if split is None:
        return image
    bands = split()
    if not isinstance(bands, tuple) or len(bands) != 3:
        return image
    red_band, green_band, blue_band = bands
    try:
        red_mask = _ink_mask(chops, red_band, green_band, blue_band)
        blue_mask = _ink_mask(chops, blue_band, red_band, green_band)
        lighter = getattr(chops, "lighter", None)
        if lighter is None:
            return image
        mask = lighter(red_mask, blue_mask)
        white = pillow.new("RGB", size, (255, 255, 255))
        composite = getattr(pillow, "composite", None)
        if composite is None:
            return image
        cleaned: object = composite(white, rgb, mask)
    except (TypeError, ValueError, OSError):
        return image
    return cleaned


def achromatic_stamp_overlap(image: object) -> bool:
    """Толстое тёмное кольцо по четырём краям кропа и чернила внутри.

    Цветная печать к этому моменту уже белая. Волосная рамка ячейки,
    подчёркивание и строка с белыми полями кольцом не являются.
    Срабатывание значит: участок не читается.
    """

    convert = getattr(image, "convert", None)
    resize = getattr(image, "resize", None)
    if convert is None:
        return False
    gray = convert("L")
    size = _image_size(gray)
    if size is None:
        return False
    width, height = size
    if width < 24 or height < 24:
        return False
    if max(width, height) > 180 and resize is not None:
        scale = 180 / max(width, height)
        gray = gray.resize((max(24, int(width * scale)), max(24, int(height * scale))))
        resized = _image_size(gray)
        if resized is None:
            return False
        width, height = resized
    reader = getattr(gray, "get_flattened_data", None)
    if reader is None:
        reader = getattr(gray, "getdata", None)
    if reader is None:
        return False
    pixels = [int(item) for item in reader()]
    if len(pixels) != width * height:
        return False
    margin_x = max(2, int(width * 0.12))
    margin_y = max(2, int(height * 0.12))

    def row_ink(y: int, x0: int, x1: int) -> float:
        if x1 <= x0:
            return 0.0
        ink = sum(1 for x in range(x0, x1) if pixels[y * width + x] < 90)
        return ink / (x1 - x0)

    def column_ink(x: int, y0: int, y1: int) -> float:
        if y1 <= y0:
            return 0.0
        ink = sum(1 for y in range(y0, y1) if pixels[y * width + x] < 90)
        return ink / (y1 - y0)

    def thickness(fractions: list[float]) -> int:
        return sum(1 for item in fractions if item >= 0.55)

    top = thickness([row_ink(y, 0, width) for y in range(margin_y)])
    bottom = thickness(
        [row_ink(y, 0, width) for y in range(height - margin_y, height)]
    )
    left = thickness([column_ink(x, 0, height) for x in range(margin_x)])
    right = thickness(
        [column_ink(x, 0, height) for x in range(width - margin_x, width)]
    )
    inner_ink = 0
    inner_total = 0
    for y in range(margin_y, height - margin_y):
        for x in range(margin_x, width - margin_x):
            inner_total += 1
            if pixels[y * width + x] < 90:
                inner_ink += 1
    inner = (inner_ink / inner_total) if inner_total else 0.0
    # Толщина ≥ 3 отсекает волосную рамку ячейки и подчёркивание.
    return min(top, bottom, left, right) >= 3 and inner > 0.04


def image_bytes_have_stamp(data: bytes) -> bool:
    """Кроп пилота с чёрной печатью. Такие строки не входят в знаменатель CA."""

    if not data:
        return False
    try:
        pillow = import_module("PIL.Image")
    except ImportError:
        return False
    open_image = getattr(pillow, "open", None)
    if open_image is None:
        return False
    try:
        image = open_image(BytesIO(data))
    except (OSError, ValueError):
        return False
    return achromatic_stamp_overlap(image)


def value_region_unreadable(
    data: bytes,
    *,
    page_number: int,
    frame: PageFrame,
    polygon: Polygon,
    cache: PageImageCache | None = None,
) -> bool:
    """Кроп значения закрыт чёрной печатью. Без кадра страницы — False."""

    if cache is None:
        return False
    region = expand_user_region(polygon, frame)
    if region is None:
        return False
    image = cache.page_image(page_number)
    full_size = _image_size(image)
    box = None if full_size is None else _crop_pixels(frame, region, full_size)
    cropped = _crop_image(image, box)
    if cropped is None:
        return False
    return achromatic_stamp_overlap(cropped)


def unrotate_norm(nx: float, ny: float, quarter_ccw: int) -> tuple[float, float]:
    """Точка кадра, повёрнутого против часовой на quarter*90, в исходном кадре."""

    if quarter_ccw == 0:
        return (nx, ny)
    if quarter_ccw == 1:
        return (1.0 - ny, nx)
    if quarter_ccw == 2:
        return (1.0 - nx, 1.0 - ny)
    if quarter_ccw == 3:
        return (ny, 1.0 - nx)
    raise ValueError(f"четверть {quarter_ccw} не из 0..3")


def _ocr_image(image: object, page: PdfPageTokens, size: tuple[int, int]) -> tuple[PageToken, ...]:
    from kontur.infrastructure.ocr_rapid import rapid_page_tokens

    image = suppress_colored_seal(image)

    rapid = rapid_page_tokens(image, page, size)
    if rapid:
        return rapid
    try:
        pytesseract = import_module("pytesseract")
    except ImportError:
        return ()
    payload = _image_to_data(pytesseract, image, psm=6)
    if payload is None:
        return ()
    return tokens_from_tesseract_payload(payload, page, size)


def _view_page(page: PdfPageTokens, size: tuple[int, int]) -> PdfPageTokens:
    width, height = float(size[0]), float(size[1])
    frame = PageFrame(media=(0.0, 0.0, width, height), crop=(0.0, 0.0, width, height), rotate=0)
    return replace(page, frame=frame, tokens=())


def _remap_turn(
    tokens: tuple[PageToken, ...],
    quarter_ccw: int,
    page: PdfPageTokens,
) -> tuple[PageToken, ...]:
    mapped: list[PageToken] = []
    for token in tokens:
        points: list[tuple[float, float]] = []
        for nx, ny in token.polygon_norm:
            ux, uy = unrotate_norm(nx, ny, quarter_ccw)
            if ux < -1e-6 or uy < -1e-6 or ux > 1.0 + 1e-6 or uy > 1.0 + 1e-6:
                points = []
                break
            points.append((min(1.0, max(0.0, ux)), min(1.0, max(0.0, uy))))
        if len(points) < 3:
            continue
        norm: Polygon = tuple(points)
        mapped.append(
            replace(
                token,
                polygon_norm=norm,
                polygon_source=to_source(norm, page.frame),
                page=page.page,
            )
        )
    return tuple(mapped)


def _ocr_turned_image(image: object, page: PdfPageTokens) -> tuple[PageToken, ...]:
    """90/180/270, если прямой кадр пуст. /Rotate уже учтён рендером и сюда не входит."""

    try:
        pillow = import_module("PIL.Image")
    except ImportError:
        return ()
    transpose = getattr(pillow, "Transpose", None)
    turn = getattr(image, "transpose", None)
    if transpose is None or turn is None:
        return ()
    best: tuple[PageToken, ...] = ()
    for quarter, operation in (
        (1, transpose.ROTATE_90),
        (2, transpose.ROTATE_180),
        (3, transpose.ROTATE_270),
    ):
        try:
            turned = turn(operation)
        except (TypeError, ValueError, OSError):
            continue
        turned_size = _image_size(turned)
        if turned_size is None:
            continue
        found = _ocr_image(turned, _view_page(page, turned_size), turned_size)
        mapped = _remap_turn(found, quarter, page)
        if len(mapped) > len(best):
            best = mapped
    return best


def _ocr_pdf_page(pdf_page: object, page: PdfPageTokens) -> tuple[PageToken, ...]:
    image = _render_pil(pdf_page)
    size = _image_size(image)
    if image is None or size is None:
        return ()
    tokens = _ocr_image(image, page, size)
    if tokens:
        return tokens
    return _ocr_turned_image(image, page)


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
