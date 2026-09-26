"""RapidOCR по локальным весам. Сеть в рантайме не используется.

`ocr_text` этим модулем не становится AVAILABLE: порог гейта I не снят.
Нет каталога, битая сумма или нет пакета — вызывающий остаётся на Tesseract.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import replace
from functools import lru_cache
from importlib import import_module
from pathlib import Path

from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import polygons_from_view_pixels
from kontur.domain.models import ExtractionEngine
from kontur.infrastructure.pdfium_tokens import PdfPageTokens

WEIGHTS_ENV = "KONTUR_OCR_WEIGHTS"
_LOCK_PATH = Path(__file__).with_name("ocr_weights.lock.json")
_MIN_SCORE = 0.40


def _lock_files() -> tuple[dict[str, str], ...]:
    try:
        payload = json.loads(_LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if payload.get("runtime_download") is not False:
        return ()
    files = payload.get("files")
    if not isinstance(files, list):
        return ()
    out: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            return ()
        role = item.get("role")
        name = item.get("name")
        digest = item.get("sha256")
        if not isinstance(role, str) or not isinstance(name, str) or not isinstance(digest, str):
            return ()
        out.append({"role": role, "name": name, "sha256": digest})
    return tuple(out)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def weights_ready() -> bool:
    """Каталог из окружения совпадает с замком. Скачивания нет."""

    raw = os.environ.get(WEIGHTS_ENV, "").strip()
    if not raw:
        return False
    root = Path(raw)
    files = _lock_files()
    if not files:
        return False
    for item in files:
        path = root / item["name"]
        if not path.is_file():
            return False
        if _sha256(path) != item["sha256"]:
            return False
    return True


def _paths() -> dict[str, Path] | None:
    if not weights_ready():
        return None
    root = Path(os.environ[WEIGHTS_ENV])
    return {item["role"]: root / item["name"] for item in _lock_files()}


def _enum(module: object, enum_name: str, member: str, fallback: str) -> object:
    """RapidOCR 3.x принимает в конфиге только свои Enum, строку отвергает."""

    holder = getattr(module, enum_name, None)
    if holder is None:
        return fallback
    return getattr(holder, member, fallback)


def _engine_params(module: object, paths: dict[str, Path]) -> dict[str, object]:
    onnx = _enum(module, "EngineType", "ONNXRUNTIME", "onnxruntime")
    v5 = _enum(module, "OCRVersion", "PPOCRV5", "PP-OCRv5")
    mobile = _enum(module, "ModelType", "MOBILE", "mobile")
    return {
        "Global.use_det": True,
        "Global.use_cls": True,
        "Global.use_rec": True,
        "Global.log_level": "warning",
        "Det.engine_type": onnx,
        "Det.ocr_version": v5,
        "Det.model_type": mobile,
        "Det.model_path": str(paths["det"]),
        "Cls.engine_type": onnx,
        "Cls.ocr_version": v5,
        "Cls.model_type": mobile,
        "Cls.model_path": str(paths["cls"]),
        "Rec.engine_type": onnx,
        "Rec.ocr_version": v5,
        "Rec.model_type": mobile,
        "Rec.lang_type": _enum(module, "LangRec", "ESLAV", "eslav"),
        "Rec.model_path": str(paths["rec"]),
        "Rec.rec_keys_path": str(paths["dict"]),
    }


@lru_cache(maxsize=1)
def _engine() -> object | None:
    paths = _paths()
    if paths is None:
        return None
    try:
        module = import_module("rapidocr")
    except ImportError:
        return None
    ctor = getattr(module, "RapidOCR", None)
    if ctor is None:
        return None
    try:
        built: object = ctor(params=_engine_params(module, paths))
    except (OSError, RuntimeError, ValueError, TypeError, ImportError):
        return None
    return built


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _rows(value: object) -> list[object] | None:
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        return None
    return list(value)


def _as_points(box: object) -> list[tuple[float, float]]:
    rows = _rows(box)
    if rows is None:
        return []
    points: list[tuple[float, float]] = []
    for point in rows:
        if isinstance(point, str | bytes):
            return []
        try:
            pair = _rows(point)
        except TypeError:
            return []
        if pair is None or len(pair) < 2 or isinstance(pair[0], bool) or isinstance(pair[1], bool):
            return []
        try:
            points.append((float(pair[0]), float(pair[1])))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return []
    return points


def _token(
    text: str,
    score: float,
    points: list[tuple[float, float]],
    page: PdfPageTokens,
    image_size: tuple[int, int],
) -> PageToken | None:
    if score < _MIN_SCORE or len(points) < 4:
        return None
    img_w, img_h = image_size
    if img_w <= 0 or img_h <= 0:
        return None
    xs = [item[0] for item in points]
    ys = [item[1] for item in points]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    if right <= left or bottom <= top:
        return None
    mapped = polygons_from_view_pixels(left, top, right, bottom, image_size, page.frame)
    if mapped is None:
        return None
    polygon, polygon_norm = mapped
    return PageToken(
        text=text,
        page=page.page,
        polygon_source=polygon,
        polygon_norm=polygon_norm,
        engine=ExtractionEngine.OCR,
    )


def _words(result: object, page: PdfPageTokens, image_size: tuple[int, int]) -> list[PageToken]:
    word_results = getattr(result, "word_results", None)
    tokens: list[PageToken] = []
    if isinstance(word_results, (list, tuple)) and any(word_results):
        for line in word_results:
            if not isinstance(line, (list, tuple)):
                continue
            for item in line:
                if not isinstance(item, (list, tuple)) or len(item) < 3:
                    continue
                text, score, box = item[0], item[1], item[2]
                if not isinstance(text, str) or isinstance(score, bool):
                    continue
                score_value = _as_float(score)
                if score_value is None:
                    continue
                token = _token(text.strip(), score_value, _as_points(box), page, image_size)
                if token is not None:
                    tokens.append(token)
        if tokens:
            return tokens
    lines = _rows(getattr(result, "txts", None))
    score_list = _rows(getattr(result, "scores", None))
    box_rows = _rows(getattr(result, "boxes", None))
    if lines is None or score_list is None or box_rows is None:
        return []
    for index, raw in enumerate(lines):
        if index >= len(score_list) or index >= len(box_rows):
            break
        text = str(raw or "").strip()
        score = score_list[index]
        if not text or isinstance(score, bool):
            continue
        score_value = _as_float(score)
        if score_value is None:
            continue
        token = _token(text, score_value, _as_points(box_rows[index]), page, image_size)
        if token is not None:
            tokens.append(token)
    return tokens


def rapid_available() -> bool:
    """Движок собран по весам из замка. Не прогон пилота и не capabilities."""

    return callable(_engine())


def _recognize_line(image: object) -> tuple[str, float] | None:
    """Одна строка без детектора. Пословные рамки дробят число «1200» на «1» и «200»."""

    engine = _engine()
    if not callable(engine):
        return None
    try:
        result = engine(image, use_det=False, use_cls=False, use_rec=True)
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
        return None
    texts = [str(item).strip() for item in _rows(getattr(result, "txts", None)) or []]
    scores = [_as_float(item) for item in _rows(getattr(result, "scores", None)) or []]
    known = [item for item in scores if item is not None]
    return " ".join(item for item in texts if item), min(known) if known else 0.0


def rapid_line_text(data: bytes) -> str:
    """Текст готового кропа строки: только распознавание, без детектора."""

    if not data:
        return ""
    read = _recognize_line(data)
    return "" if read is None else read[0]


def rapid_crop_tokens(
    image: object,
    page: PdfPageTokens,
    image_size: tuple[int, int],
) -> tuple[PageToken, ...] | None:
    """Кроп значения одной строкой: токен на весь кроп. None — движка нет."""

    read = _recognize_line(image)
    if read is None:
        return None
    text, score = read
    if not text:
        return ()
    width, height = image_size
    corners = [(0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height))]
    token = _token(text, score, corners, page, image_size)
    if token is None:
        return ()
    from kontur.infrastructure.ocr_tesseract import fold_token_texts

    return (replace(token, text=fold_token_texts([token.text])[0]),)


def rapid_page_tokens(
    image: object,
    page: PdfPageTokens,
    image_size: tuple[int, int],
) -> tuple[PageToken, ...] | None:
    """Слова страницы или None, если движок недоступен. Пустой кортеж — прочитал и пусто."""

    engine = _engine()
    if not callable(engine):
        return None
    try:
        result = engine(image, use_cls=True, return_word_box=True)
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError):
        return None
    tokens = _words(result, page, image_size)
    if not tokens:
        return ()
    from kontur.infrastructure.ocr_tesseract import fold_token_texts

    folded = fold_token_texts([token.text for token in tokens])
    return tuple(replace(token, text=text) for token, text in zip(tokens, folded, strict=True))
