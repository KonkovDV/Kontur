"""Ведомость: в строке марка и одно число. Набор марок должен совпасть.

Чужую строку не подбираем. Два числа в одной строке — не ведомость.
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
class TableRow:
    mark: str
    value: float
    page: int
    polygon_source: Polygon
    polygon_norm: Polygon


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
            if (
                token.page == group[0].page
                and y_overlap(group[0].polygon_norm, token.polygon_norm)
            ):
                group.append(token)
                placed = True
                break
        if not placed:
            grouped.append([token])
    return grouped


def parse_element_table(tokens: Sequence[PageToken]) -> dict[str, TableRow] | str:
    """Марка → строка. Пустая ведомость и повтор марки — текст причины."""

    found: dict[str, TableRow] = {}
    for group in _rows(tokens):
        numbers = [item for item in group if _NUMBER.fullmatch(item.text.strip())]
        if not numbers:
            continue
        if len(numbers) != 1:
            return "строка с несколькими числами"
        marks = [item for item in group if item not in numbers and item.text.strip()]
        if not marks:
            continue
        mark = "".join(item.text.strip() for item in marks)
        if mark in found:
            return f"марка {mark} повторяется"
        try:
            value = parse_number(numbers[0].text.strip(), ("nfc", "decimal_comma"))
        except ValueError:
            return "число строки не разбирается"
        polygons_source = tuple(item.polygon_source for item in (*marks, numbers[0]))
        polygons_norm = tuple(item.polygon_norm for item in (*marks, numbers[0]))
        found[mark] = TableRow(
            mark=mark,
            value=value,
            page=numbers[0].page,
            polygon_source=union_rect_polygon(polygons_source),
            polygon_norm=union_rect_polygon(polygons_norm),
        )
    if not found:
        return "строки ведомости не найдены"
    return found


def align_tables(
    left: dict[str, TableRow],
    right: dict[str, TableRow],
    rule: dict[str, object],
) -> tuple[Comparison, str] | str:
    """Первое расхождение по допуску правила. Разный набор марок не сравниваем."""

    if set(left) != set(right):
        return "набор элементов не совпал"
    chosen: Comparison | None = None
    chosen_mark = ""
    for mark in sorted(left):
        comparison = compare_delta(left[mark].value, right[mark].value, rule)
        if comparison.status is FindingStatus.CANDIDATE:
            return comparison, mark
        if chosen is None:
            chosen = comparison
            chosen_mark = mark
    if chosen is None:
        return "строки ведомости не найдены"
    return chosen, chosen_mark


def row_hit(row: TableRow, rule: dict[str, object], tokens: Sequence[PageToken]) -> NumberHit:
    return NumberHit(
        extraction=Extraction(
            raw_token=row.mark,
            engine=engine_of(tokens),
            engine_version=ENGINE_VERSION,
            confidence=0.99,
            normalized_value=row.value,
            unit=str(rule["unit"]) if rule.get("unit") else None,
            grounded_in_source_tokens=True,
            second_read_agrees=True,
            confidence_features={},
        ),
        page=row.page,
        polygon_source=row.polygon_source,
        polygon_norm=row.polygon_norm,
        window_text=row.mark,
    )
