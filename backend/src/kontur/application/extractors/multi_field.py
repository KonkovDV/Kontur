"""Несколько полей одного пункта: число только рядом с явной единицей.

Единицы берутся из `unit` правила, разделитель « / ». Голое число не
приписывается ни одному полю и не переводится в другую единицу. Повтор
одного поля и отсутствующее поле — не сравнение. Подсчёт фигур на листе
сюда не входит.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from kontur.application.comparators import Comparison, compare_delta
from kontur.application.extractors.number import (
    ENGINE_VERSION,
    NumberHit,
    PageToken,
    engine_of,
)
from kontur.application.normalize import parse_number
from kontur.domain.geometry import union_rect_polygon, y_overlap
from kontur.domain.models import Extraction, Polygon
from kontur.domain.statuses import FindingStatus

_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")


@dataclass(frozen=True, slots=True)
class FieldHit:
    unit: str
    value: float
    page: int
    polygon_source: Polygon
    polygon_norm: Polygon


def _unit_key(text: str) -> str:
    return text.strip().casefold().rstrip(".")


def field_units(rule: dict[str, object]) -> tuple[str, ...] | str:
    """Единицы пункта в порядке правила. Одной единицы недостаточно."""

    raw = rule.get("unit")
    if not isinstance(raw, str) or " / " not in raw:
        return "в пункте нет нескольких полей"
    parts = tuple(part.strip() for part in raw.split(" / ") if part.strip())
    if len(parts) < 2 or len({_unit_key(part) for part in parts}) != len(parts):
        return "в пункте нет нескольких полей"
    comparator = rule.get("comparator")
    if not isinstance(comparator, dict) or comparator.get("operator") != "delta":
        return "сравнение нескольких полей ждёт оператор delta"
    return parts


def _rows(tokens: Sequence[PageToken]) -> list[list[PageToken]]:
    grouped: list[list[PageToken]] = []
    ordered = sorted(
        tokens,
        key=lambda item: (item.page, item.polygon_norm[0][1], item.polygon_norm[0][0]),
    )
    for token in ordered:
        if ":" in token.text:
            continue
        placed = False
        for group in grouped:
            if token.page == group[0].page and y_overlap(group[0].polygon_norm, token.polygon_norm):
                group.append(token)
                placed = True
                break
        if not placed:
            grouped.append([token])
    return grouped


def parse_fields(
    tokens: Sequence[PageToken],
    rule: dict[str, object],
) -> dict[str, FieldHit] | str:
    """Каждая единица правила — ровно одно число следом за ней."""

    units = field_units(rule)
    if isinstance(units, str):
        return units
    known = {_unit_key(unit): unit for unit in units}
    found: dict[str, FieldHit] = {}
    for group in _rows(tokens):
        ordered = sorted(group, key=lambda item: item.polygon_norm[0][0])
        index = 0
        while index < len(ordered) - 1:
            number = ordered[index]
            unit_token = ordered[index + 1]
            unit = known.get(_unit_key(unit_token.text))
            if _NUMBER.fullmatch(number.text.strip()) is None or unit is None:
                index += 1
                continue
            if unit in found:
                return f"поле {unit} повторяется"
            try:
                value = parse_number(number.text.strip(), ("nfc", "decimal_comma"))
            except ValueError:
                return f"поле {unit} не разбирается"
            source = union_rect_polygon((number.polygon_source, unit_token.polygon_source))
            norm = union_rect_polygon((number.polygon_norm, unit_token.polygon_norm))
            found[unit] = FieldHit(
                unit=unit,
                value=value,
                page=number.page,
                polygon_source=source,
                polygon_norm=norm,
            )
            index += 2
    for unit in units:
        if unit not in found:
            return f"поле {unit} не найдено"
    return found


def align_fields(
    left: dict[str, FieldHit],
    right: dict[str, FieldHit],
    rule: dict[str, object],
) -> tuple[Comparison, str] | str:
    """Первое расхождение по допуску правила. Поля не переводятся друг в друга."""

    units = field_units(rule)
    if isinstance(units, str):
        return units
    if set(left) != set(units) or set(right) != set(units):
        return "набор полей не совпал"
    chosen: Comparison | None = None
    chosen_unit = ""
    for unit in units:
        scoped = dict(rule)
        scoped["unit"] = unit
        comparison = compare_delta(left[unit].value, right[unit].value, scoped)
        if comparison.status is FindingStatus.CANDIDATE:
            return comparison, unit
        if chosen is None:
            chosen = comparison
            chosen_unit = unit
    if chosen is None:
        return "поля не найдены"
    return chosen, chosen_unit


def field_hit(field: FieldHit, tokens: Sequence[PageToken]) -> NumberHit:
    return NumberHit(
        extraction=Extraction(
            raw_token=f"{field.value} {field.unit}",
            engine=engine_of(tokens),
            engine_version=ENGINE_VERSION,
            confidence=0.99,
            normalized_value=field.value,
            unit=field.unit,
            grounded_in_source_tokens=True,
            second_read_agrees=True,
            confidence_features={},
        ),
        page=field.page,
        polygon_source=field.polygon_source,
        polygon_norm=field.polygon_norm,
        window_text=field.unit,
    )
