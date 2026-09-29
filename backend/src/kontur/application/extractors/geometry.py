"""Ширина пары штрихов как число для компаратора.

Контрактный тип — geometry, не drawing_dimension. Живое IOS4-078 остаётся
number: текстовое A×B не подменяется обмером. Пороги читаются из
extractor.params (иначе geometry_params). Второе чтение — подпись размера
рядом с контуром; нет подписи не считается расхождением.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from kontur.application.extractors.drawing_scale import STAMP_Y, scale_mark
from kontur.application.extractors.number import ENGINE_VERSION, NumberHit, PageToken
from kontur.application.normalize import scale_length_to_target
from kontur.domain.coordinates import PageFrame
from kontur.domain.geometry import bbox_from_polygon
from kontur.domain.models import Extraction, ExtractionEngine, Polygon
from kontur.infrastructure.duct_geometry import (
    DEFAULT_ANGLE_DEG,
    DEFAULT_GAP_MAX_PT,
    DEFAULT_GAP_MIN_PT,
    DEFAULT_LABEL_MAX_NORM,
    DEFAULT_MIN_LENGTH_PT,
    DEFAULT_MIN_OVERLAP,
    DEFAULT_READ_TOLERANCE_REL,
    duct_section,
    gaps_agree,
    pair_parallel,
    segments_on_page,
    width_mm,
)

_PAIR = re.compile(r"(\d{2,4}(?:[.,]\d+)?)\s*[×xх]\s*(\d{2,4}(?:[.,]\d+)?)")
_SIDE = re.compile(r"(?<![0-9])(\d{2,4}(?:[.,]\d+)?)(?![0-9])")


def _number(raw: dict[str, object], key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"extractor.params.{key} должен быть числом")
    return float(value)


def _raw_params(rule: dict[str, object]) -> dict[str, object]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return {}
    raw = extractor.get("params")
    if raw is None:
        raw = extractor.get("geometry_params")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("extractor.params должен быть объектом")
    return raw


def geometry_params(rule: dict[str, object]) -> dict[str, float]:
    """Пороги из extractor.params.

    Пропуск ключа — заранее заданная константа, не подгон по золоту.
    """

    raw = _raw_params(rule)
    params = {
        "angle_deg": _number(raw, "angle_deg", DEFAULT_ANGLE_DEG),
        "min_overlap": _number(raw, "min_overlap", DEFAULT_MIN_OVERLAP),
        "min_length_pt": _number(raw, "min_length_pt", DEFAULT_MIN_LENGTH_PT),
        "gap_min_pt": _number(raw, "gap_min_pt", DEFAULT_GAP_MIN_PT),
        "gap_max_pt": _number(raw, "gap_max_pt", DEFAULT_GAP_MAX_PT),
        "stamp_y": _number(raw, "stamp_y", STAMP_Y),
        "read_tolerance_rel": _number(raw, "read_tolerance_rel", DEFAULT_READ_TOLERANCE_REL),
        "label_max_norm": _number(raw, "label_max_norm", DEFAULT_LABEL_MAX_NORM),
    }
    if not 0 < params["angle_deg"] <= 45:
        raise ValueError("angle_deg должен быть в (0; 45]")
    if not 0 < params["min_overlap"] <= 1:
        raise ValueError("min_overlap должен быть в (0; 1]")
    if params["min_length_pt"] <= 0:
        raise ValueError("min_length_pt должен быть > 0")
    if params["gap_min_pt"] <= 0 or params["gap_min_pt"] >= params["gap_max_pt"]:
        raise ValueError("зазор: 0 < gap_min_pt < gap_max_pt")
    if not 0 < params["stamp_y"] < 1:
        raise ValueError("stamp_y должен быть в (0; 1)")
    if not 0 <= params["read_tolerance_rel"] <= 1:
        raise ValueError("read_tolerance_rel должен быть в [0; 1]")
    if not 0 < params["label_max_norm"] <= 1:
        raise ValueError("label_max_norm должен быть в (0; 1]")
    return params


def _millimetres(text: str) -> float:
    return float(text.replace(",", "."))


def _label_mm(text: str, width_mm: float) -> float | None:
    pair = _PAIR.search(text)
    if pair:
        sides = (_millimetres(pair.group(1)), _millimetres(pair.group(2)))
        return min(sides, key=lambda item: abs(item - width_mm))
    single = _SIDE.search(text)
    if single is None:
        return None
    return _millimetres(single.group(1))


def _distance(px: float, py: float, box: tuple[float, float, float, float]) -> float:
    left, top, right, bottom = box
    dx = max(left - px, 0.0, px - right)
    dy = max(top - py, 0.0, py - bottom)
    return math.hypot(dx, dy)


def _nearby_label(
    tokens: Sequence[PageToken],
    page: int,
    polygon_norm: Polygon,
    width_mm: float,
    radius: float,
) -> float | None:
    box = bbox_from_polygon(polygon_norm)
    best: float | None = None
    best_dist = radius
    seen = False
    for token in tokens:
        if token.page != page:
            continue
        value = _label_mm(token.text, width_mm)
        if value is None:
            continue
        xs = [point[0] for point in token.polygon_norm]
        ys = [point[1] for point in token.polygon_norm]
        dist = _distance((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, box)
        if dist <= radius and (not seen or dist < best_dist):
            best = value
            best_dist = dist
            seen = True
    return best


def _length_target(rule: dict[str, object]) -> str | None:
    """Единица правила. Обмер сам задаёт миллиметры, голый текст сюда не входит."""

    comparator = rule.get("comparator")
    if isinstance(comparator, dict):
        raw = comparator.get("unit_target")
        if isinstance(raw, str) and raw.strip():
            return raw
    unit = rule.get("unit")
    return unit if isinstance(unit, str) and unit.strip() else None


def extract_duct_width(
    tokens: Sequence[PageToken],
    pdf_bytes: bytes | None,
    frames: Sequence[PageFrame],
    rule: dict[str, object],
) -> tuple[NumberHit | None, str]:
    """Ширина в единице правила. Обмер даёт миллиметры; голый текст не переводится."""

    params = geometry_params(rule)
    mark = scale_mark(tokens, stamp_y=params["stamp_y"])
    if mark is None:
        return None, "масштаб в штампе не найден"
    page_number, scale = mark
    if not pdf_bytes:
        return None, "нет PDF для обмера штрихов"
    if page_number > len(frames):
        return None, "нет рамки страницы для нормализации"
    try:
        segments = segments_on_page(pdf_bytes, page_number)
    except ValueError as exc:
        return None, str(exc)
    pairs = pair_parallel(
        segments,
        scale,
        angle_deg=params["angle_deg"],
        min_overlap=params["min_overlap"],
        min_length_pt=params["min_length_pt"],
        gap_min_pt=params["gap_min_pt"],
        gap_max_pt=params["gap_max_pt"],
    )
    if len(pairs) != 1:
        if not pairs:
            return None, "пара параллельных штрихов не найдена"
        return None, "несколько пар штрихов"
    chosen = pairs[0]
    try:
        section = duct_section(chosen, frames[page_number - 1], page_number)
    except ValueError:
        return None, "контур сечения вне страницы"
    tolerance = params["read_tolerance_rel"]
    agrees = gaps_agree(chosen.gap_pt, chosen.reverse_gap_pt, tolerance_rel=tolerance)
    label = _nearby_label(
        tokens,
        page_number,
        section.polygon_norm,
        section.width_mm,
        params["label_max_norm"],
    )
    if label is not None and not gaps_agree(section.width_mm, label, tolerance_rel=tolerance):
        agrees = False
    value = scale_length_to_target(
        section.width_mm,
        source_unit="мм",
        target_unit=_length_target(rule),
    )
    reverse_mm = width_mm(chosen.reverse_gap_pt, scale)
    features = {
        "gap_pt": chosen.gap_pt,
        "reverse_gap_pt": chosen.reverse_gap_pt,
        "reverse_mm": reverse_mm,
        "measured_mm": section.width_mm,
        "scale": float(scale),
    }
    if label is not None:
        features["label_mm"] = label
    return (
        NumberHit(
            extraction=Extraction(
                raw_token=f"{value:.4f}",
                engine=ExtractionEngine.VECTOR,
                engine_version=ENGINE_VERSION,
                confidence=0.99 if agrees else 0.4,
                normalized_value=value,
                unit=str(rule["unit"]) if rule.get("unit") else None,
                grounded_in_source_tokens=True,
                second_read_agrees=agrees,
                confidence_features=features,
            ),
            page=section.page,
            polygon_source=chosen.polygon,
            polygon_norm=section.polygon_norm,
            window_text=f"1:{scale} {value:.4f}",
        ),
        "",
    )
