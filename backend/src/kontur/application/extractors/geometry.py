"""Ширина пары штрихов как число для компаратора.

Живое правило IOS4-078 остаётся extractor.type=number: текстовое A×B
не подменяется обмером, пока параметры не заморожены на неразмеченных листах.
Этот модуль включается только у правила с type=geometry.
"""

from __future__ import annotations

from collections.abc import Sequence

from kontur.application.extractors.drawing_scale import STAMP_Y, scale_mark
from kontur.application.extractors.number import ENGINE_VERSION, NumberHit, PageToken
from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.models import Extraction, ExtractionEngine
from kontur.infrastructure.duct_geometry import (
    DEFAULT_ANGLE_DEG,
    DEFAULT_GAP_MAX_PT,
    DEFAULT_GAP_MIN_PT,
    DEFAULT_MIN_LENGTH_PT,
    DEFAULT_MIN_OVERLAP,
    DEFAULT_READ_TOLERANCE_REL,
    choose_pair,
    gaps_agree,
    pair_parallel,
    segments_on_page,
    width_mm,
)


def _number(raw: dict[str, object], key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"geometry_params.{key} должен быть числом")
    return float(value)


def geometry_params(rule: dict[str, object]) -> dict[str, float]:
    """Пороги из правила или заранее заданные константы модуля штрихов."""

    extractor = rule.get("extractor")
    raw = extractor.get("geometry_params") if isinstance(extractor, dict) else None
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("geometry_params должен быть объектом")
    params = {
        "angle_deg": _number(raw, "angle_deg", DEFAULT_ANGLE_DEG),
        "min_overlap": _number(raw, "min_overlap", DEFAULT_MIN_OVERLAP),
        "min_length_pt": _number(raw, "min_length_pt", DEFAULT_MIN_LENGTH_PT),
        "gap_min_pt": _number(raw, "gap_min_pt", DEFAULT_GAP_MIN_PT),
        "gap_max_pt": _number(raw, "gap_max_pt", DEFAULT_GAP_MAX_PT),
        "stamp_y": _number(raw, "stamp_y", STAMP_Y),
        "read_tolerance_rel": _number(raw, "read_tolerance_rel", DEFAULT_READ_TOLERANCE_REL),
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
    return params


def extract_duct_width(
    tokens: Sequence[PageToken],
    pdf_bytes: bytes | None,
    frames: Sequence[PageFrame],
    rule: dict[str, object],
) -> tuple[NumberHit | None, str]:
    """Ширина в мм. None и текст причины — нет масштаба, листа или пары."""

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
    chosen = choose_pair(pairs)
    if chosen is None:
        return None, "пара параллельных штрихов не найдена"
    try:
        polygon_norm = to_normalized(chosen.polygon, frames[page_number - 1])
    except ValueError:
        return None, "контур сечения вне страницы"
    agrees = gaps_agree(
        chosen.gap_pt,
        chosen.reverse_gap_pt,
        tolerance_rel=params["read_tolerance_rel"],
    )
    reverse_mm = width_mm(chosen.reverse_gap_pt, scale)
    return (
        NumberHit(
            extraction=Extraction(
                raw_token=f"{chosen.width_mm:.2f}",
                engine=ExtractionEngine.VECTOR,
                engine_version=ENGINE_VERSION,
                confidence=0.99 if agrees else 0.4,
                normalized_value=chosen.width_mm,
                unit=str(rule["unit"]) if rule.get("unit") else None,
                grounded_in_source_tokens=True,
                second_read_agrees=agrees,
                confidence_features={
                    "gap_pt": chosen.gap_pt,
                    "reverse_gap_pt": chosen.reverse_gap_pt,
                    "reverse_mm": reverse_mm,
                    "scale": float(scale),
                },
            ),
            page=page_number,
            polygon_source=chosen.polygon,
            polygon_norm=polygon_norm,
            window_text=f"1:{scale} {chosen.width_mm:.2f}",
        ),
        "",
    )
