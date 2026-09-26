"""Площадь одного замкнутого прямоугольника на листе.

Границы объекта pdfium чуть шире штриха. Сравнение идёт ПД с РД, поэтому
одинаковый штрих на обеих сторонах не становится расхождением. Несколько
контуров не суммируются. Пороги не подбираются по золоту.
"""

from __future__ import annotations

import ctypes

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from kontur.application.extractors.drawing_scale import STAMP_Y, scale_mark
from kontur.application.extractors.number import ENGINE_VERSION, NumberHit, PageToken
from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.models import Extraction, ExtractionEngine, Polygon
from kontur.infrastructure.duct_geometry import PT_TO_MM

DEFAULT_MIN_SIDE_PT = 8.0
DEFAULT_MAX_PAGE_FRACTION = 0.85


def _number(raw: dict[str, object], key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"extractor.params.{key} должен быть числом")
    return float(value)


def _params(rule: dict[str, object]) -> dict[str, float]:
    extractor = rule.get("extractor")
    raw = extractor.get("params") if isinstance(extractor, dict) else None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("extractor.params должен быть объектом")
    params = {
        "min_side_pt": _number(raw, "min_side_pt", DEFAULT_MIN_SIDE_PT),
        "max_page_fraction": _number(raw, "max_page_fraction", DEFAULT_MAX_PAGE_FRACTION),
        "stamp_y": _number(raw, "stamp_y", STAMP_Y),
    }
    if params["min_side_pt"] <= 0:
        raise ValueError("min_side_pt должен быть > 0")
    if not 0 < params["max_page_fraction"] < 1:
        raise ValueError("max_page_fraction должен быть в (0; 1)")
    if not 0 < params["stamp_y"] < 1:
        raise ValueError("stamp_y должен быть в (0; 1)")
    return params


def _quad(left: float, bottom: float, right: float, top: float) -> Polygon:
    return ((left, bottom), (right, bottom), (right, top), (left, top))


def _rectangles(
    data: bytes,
    page_number: int,
    *,
    min_side_pt: float,
    max_page_fraction: float,
    page_area: float,
) -> list[tuple[float, float, float, float]]:
    document = pdfium.PdfDocument(data)
    try:
        page = document[page_number - 1]
        found: list[tuple[float, float, float, float]] = []
        objects = iter(page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=0))
        while True:
            try:
                obj = next(objects)
            except StopIteration:
                break
            try:
                left, bottom, right, top = (float(value) for value in obj.get_bounds())
            except ctypes.ArgumentError:
                continue
            finally:
                obj.close()
            width = right - left
            height = top - bottom
            if width < min_side_pt or height < min_side_pt:
                continue
            if page_area > 0 and (width * height) / page_area > max_page_fraction:
                continue
            found.append((left, bottom, right, top))
        return found
    finally:
        document.close()


def extract_contour_area(
    tokens: tuple[PageToken, ...] | list[PageToken],
    pdf_bytes: bytes | None,
    frames: tuple[PageFrame, ...],
    rule: dict[str, object],
) -> tuple[NumberHit | None, str]:
    """Площадь в м². Нет одного контура или масштаба — None и причина."""

    params = _params(rule)
    mark = scale_mark(tokens, stamp_y=params["stamp_y"])
    if mark is None:
        return None, "масштаб в штампе не найден"
    page_number, scale = mark
    if not pdf_bytes:
        return None, "нет PDF для обмера контура"
    if page_number > len(frames):
        return None, "нет рамки страницы для нормализации"
    frame = frames[page_number - 1]
    crop = frame.crop
    page_area = (crop[2] - crop[0]) * (crop[3] - crop[1])
    try:
        rects = _rectangles(
            pdf_bytes,
            page_number,
            min_side_pt=params["min_side_pt"],
            max_page_fraction=params["max_page_fraction"],
            page_area=page_area,
        )
    except (ValueError, pdfium.PdfiumError):
        return None, "PDF не разбирается"
    if len(rects) != 1:
        if not rects:
            return None, "замкнутый контур не найден"
        return None, "несколько замкнутых контуров"
    left, bottom, right, top = rects[0]
    width_mm = (right - left) * PT_TO_MM * scale
    height_mm = (top - bottom) * PT_TO_MM * scale
    area_m2 = (width_mm * height_mm) / 1_000_000.0
    quad = _quad(left, bottom, right, top)
    norm = to_normalized(quad, frame)
    return (
        NumberHit(
            extraction=Extraction(
                raw_token=f"{area_m2:.4f}",
                engine=ExtractionEngine.VECTOR,
                engine_version=ENGINE_VERSION,
                confidence=0.99,
                normalized_value=area_m2,
                unit="м²",
                grounded_in_source_tokens=True,
                second_read_agrees=True,
                confidence_features={"scale": float(scale), "area_m2": area_m2},
            ),
            page=page_number,
            polygon_source=quad,
            polygon_norm=norm,
            window_text=f"1:{scale} {area_m2:.4f}",
        ),
        "",
    )
