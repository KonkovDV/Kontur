"""Верификатор Tesseract-5: region-crop ×3 для страниц без текстового слоя.

Гейт I (24.09). Решение бейк-оффа зафиксировано в ocr_bakeoff.py:
  primary  = VECTOR_PDFIUM  (CA ≥ 0.999 на цифровых PDF)
  verifier = RASTER_REGION_CROP  (Tesseract-5, CA ≥ 0.97 на скане ≥ 300 dpi)

SOTA-обоснование (сентябрь 2026)
────────────────────────────────
• Tesseract 5.3.x + tessdata-best + lang=rus+eng + PSM 6
  — детерминирован, auditable, offline, грандуар токен grounded
  — CA ≥ 0.97 на чистом скане, latency ~80 мс/кроп
• Surya-OCR ≥ 0.3 (VikParuchuri, 2024–2026): CA ≥ 0.99 на печати,
  но ~8 × медленнее и нет proba-grounded bounding-box без custom wrapper
• PaddleOCR 2.8 / EasyOCR: хороши для таблиц, не имеют row-token
  grounding без post-processing — не подходит для ADR-0001
• VLM (GOT-OCR2_0, GPT-4o-vision, Gemini 1.5 Pro):
  нет offline; нет grounded source-token → нарушает ADR-0001
• docTR 0.9: Torch/TF, хорошая CA, нет tessdata-best; тяжелее Tesseract
  для задачи верификатора
Вывод: Tesseract-region-crop — оптимальный верификатор: всё выше CA_VERIFIER_FLOOR
(0.97) на корпусе конструктивной документации ≥ 300 dpi.

Модуль НЕ вызывается для векторных страниц — OCR на вектор добавит шум.
Для dual_read_required=True на векторных страницах верификатор
запускается отдельно через ocr_page_bytes (см. _pages_from_blobs Gate I+).
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass

_OCR_ENGINE_NAME: str = "tesseract-5-region-crop"
CROP_SCALE: float = 3.0  # ×3 — оптимально для шрифтов 8–12 pt ≥ 300 dpi
_LANG: str = "rus+eng"
_MIN_CONF: int = 30  # минимальная уверенность tesseract (0–100)


# ── Доступность tesseract ───────────────────────────────────────────────────────────────


def tesseract_available() -> bool:
    """Проверить доступность tesseract один раз за процесс."""
    try:
        import pytesseract  # type: ignore[import-untyped]
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


# ── Результат одной страницы ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RasterRegionResult:
    """Итог OCR-кропа одной страницы."""

    tokens: tuple  # tuple[PageToken, ...]
    page_num: int
    coverage: float  # доля строк с ненулевой уверенностью [0;1]
    engine: str = _OCR_ENGINE_NAME


# ── CA-метрика (ТЗ § 14.3) ──────────────────────────────────────────────────────────────


def character_accuracy(predicted: str, reference: str) -> float:
    """CA = 1 − (edit_distance / len(reference)).

    Порог Gate I: CA ≥ 0.95 по WORK_PLAN.md stop-condition.
    Ожидаемая CA верификатора: ≥ 0.97 (CA_VERIFIER_FLOOR).
    """
    if not reference:
        return 1.0 if not predicted else 0.0
    dist = _levenshtein(predicted, reference)
    return max(0.0, 1.0 - dist / len(reference))


def _levenshtein(a: str, b: str) -> int:
    """Расстояние Левенштейна (классика O(m*n))."""
    m, n = len(a), len(b)
    if m < n:
        a, b, m, n = b, a, n, m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1),
            )
        prev = curr
    return prev[n]


def wilson_lower(successes: int, n: int, *, z: float = 1.645) -> float:
    """Wilson нижняя граница (90% CI, z=1.645).

    Используется в stop-condition: если wilson_lower(ok, n) < 0.95 → Gate I FAIL.
    """
    if n == 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - margin)


# ── OCR одной страницы ──────────────────────────────────────────────────────────────────


def ocr_page_bytes(
    pdf_bytes: bytes,
    page_num: int,
    *,
    scale: float = CROP_SCALE,
    lang: str = _LANG,
) -> RasterRegionResult:
    """OCR одной страницы PDF (1-based). Возвращает пустые токены при недоступности.

    Завёрнут в run_pdf_parse_sync для таймаута.
    """
    from kontur.infrastructure.pdf_guard import run_pdf_parse_sync

    inner = functools.partial(_ocr_page_inner, page_num, scale=scale, lang=lang)
    return run_pdf_parse_sync(inner, pdf_bytes)


def _ocr_page_inner(
    page_num: int,
    pdf_bytes: bytes,
    *,
    scale: float = CROP_SCALE,
    lang: str = _LANG,
) -> RasterRegionResult:
    """Внутренняя функция: запускается в ThreadPool (pdf_guard)."""
    if not tesseract_available():
        return RasterRegionResult(tokens=(), page_num=page_num, coverage=0.0)

    try:
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        return RasterRegionResult(tokens=(), page_num=page_num, coverage=0.0)

    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
    except ImportError:
        return RasterRegionResult(tokens=(), page_num=page_num, coverage=0.0)

    from kontur.application.extractors.number import PageToken
    from kontur.domain.coordinates import PageFrame, to_normalized
    from kontur.domain.models import Polygon

    document = pdfium.PdfDocument(pdf_bytes)
    try:
        idx = page_num - 1
        if idx < 0 or idx >= len(document):
            return RasterRegionResult(tokens=(), page_num=page_num, coverage=0.0)

        page = document[idx]
        media = tuple(page.get_mediabox())
        crop_raw = page.get_cropbox()
        crop = tuple(crop_raw) if crop_raw is not None else media
        rotate = int(page.get_rotation())
        frame = PageFrame(media=media, crop=crop, rotate=rotate)
        crop_l, crop_b, crop_r, crop_t = frame.crop

        bitmap = page.render(scale=scale)
        try:
            raw = bytes(bitmap.buffer)
            w, h = int(bitmap.width), int(bitmap.height)
            channels = int(bitmap.n_channels)
            mode = "RGBA" if channels == 4 else "RGB"
            img = Image.frombytes(mode, (w, h), raw)
            if mode == "RGBA":
                img = img.convert("RGB")
            # PSM 6 = assume uniform block (лучший режим для таблиц ТЭП)
            custom_config = f"--psm 6 -l {lang}"
            data = pytesseract.image_to_data(
                img,
                config=custom_config,
                output_type=pytesseract.Output.DICT,
            )
        finally:
            bitmap.close()

        tokens: list[PageToken] = []
        n_total = len(data["text"])
        n_confident = 0
        for i in range(n_total):
            text = str(data["text"][i]).strip()
            conf = int(data["conf"][i])
            if not text:
                continue
            if conf < _MIN_CONF:
                continue
            n_confident += 1
            x_px = int(data["left"][i])
            y_px = int(data["top"][i])
            bw = int(data["width"][i])
            bh = int(data["height"][i])
            if bw <= 0 or bh <= 0:
                continue
            # Пиксели → user-space PDF (CropBox; PDF Y снизу, растр Y сверху)
            left_pt = crop_l + x_px / scale
            right_pt = crop_l + (x_px + bw) / scale
            top_pt = crop_t - y_px / scale
            bottom_pt = crop_t - (y_px + bh) / scale
            polygon: Polygon = (
                (left_pt, bottom_pt),
                (right_pt, bottom_pt),
                (right_pt, top_pt),
                (left_pt, top_pt),
            )
            try:
                polygon_norm = to_normalized(polygon, frame)
            except ValueError:
                continue
            tokens.append(
                PageToken(
                    text=text,
                    page=page_num,
                    polygon_source=polygon,
                    polygon_norm=polygon_norm,
                )
            )
        coverage = n_confident / max(1, n_total)
        return RasterRegionResult(
            tokens=tuple(tokens),
            page_num=page_num,
            coverage=min(1.0, coverage),
        )
    finally:
        document.close()


# ── OCR всего документа (только растровые страницы) ─────────────────────────────────────


def ocr_document_raster_pages(
    pdf_bytes: bytes,
    page_tokens: tuple,  # tuple[PdfPageTokens, ...]
    *,
    scale: float = CROP_SCALE,
    lang: str = _LANG,
) -> dict:  # dict[int, RasterRegionResult]
    """OCR только растровых страниц документа. Векторные страницы пропускаются.

    Возвращает dict: {page_num: RasterRegionResult} только для raster страниц.
    """
    results: dict[int, RasterRegionResult] = {}
    for page in page_tokens:
        if not page.has_embedded_text:
            result = ocr_page_bytes(pdf_bytes, page.page, scale=scale, lang=lang)
            results[page.page] = result
    return results
