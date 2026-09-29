"""Извлечение числа у якоря из токенов страницы.

Это L2: на вход — уже разрезанный векторный слой (или OCR-токены), не PDF.
PDF→токены — отдельный адаптер. Значение grounded, потому что совпавший текст
есть среди токенов, а не додуман моделью.

Двойное чтение здесь — два независимых прохода по одному окну: первое
совпадение regex и последнее. Одно число в ячейке — согласия; два разных —
ABSTAIN на уровне правила, а не «ближайшее к ожидаемому».
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from kontur.application.normalize import (
    fold_label,
    length_unit_of_match,
    parse_number,
    scale_length_to_target,
)
from kontur.domain.geometry import reading_key, union_rect_polygon, y_overlap
from kontur.domain.models import Extraction, ExtractionEngine, Polygon

ENGINE_VERSION = "0.1.0"

DEFAULT_NUMBER_REGEX = (
    r"(?<![0-9])(\d+(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d+)?)(?![0-9])"
)
_MAX_ANCHOR_TOKENS = 8
_MAX_WINDOW_TOKENS = 12


@dataclass(frozen=True, slots=True)
class PageToken:
    text: str
    page: int
    polygon_source: Polygon
    polygon_norm: Polygon
    engine: ExtractionEngine = ExtractionEngine.VECTOR

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("номер страницы начинается с 1, а не с 0")
        if len(self.polygon_source) < 3 or len(self.polygon_norm) < 3:
            raise ValueError("у токена должен быть polygon, а не точка")


def engine_of(tokens: Sequence[PageToken]) -> ExtractionEngine:
    """OCR только если все токены окна из OCR. Смесь не маскируем под vector."""

    engines = {item.engine for item in tokens}
    if engines == {ExtractionEngine.OCR}:
        return ExtractionEngine.OCR
    return ExtractionEngine.VECTOR


@dataclass(frozen=True, slots=True)
class NumberHit:
    extraction: Extraction
    page: int
    polygon_source: Polygon
    polygon_norm: Polygon
    window_text: str


def _sorted(tokens: Sequence[PageToken]) -> list[PageToken]:
    return sorted(tokens, key=lambda item: reading_key(item.page, item.polygon_norm))


def _anchors(rule: dict[str, object]) -> tuple[str, ...]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        raise TypeError("у правила нет extractor")
    raw = extractor.get("anchors")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{rule.get('code')}: нет якорей извлечения")
    return tuple(fold_label(str(item)) for item in raw)


def _regex(rule: dict[str, object]) -> re.Pattern[str]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        raise TypeError("у правила нет extractor")
    pattern = extractor.get("regex")
    source = pattern if isinstance(pattern, str) and pattern else DEFAULT_NUMBER_REGEX
    return re.compile(source)


_DEFAULT_NUMBER_STEPS = ("nfc", "collapse_spaces", "decimal_comma", "strip_unit")


def _steps(rule: dict[str, object]) -> tuple[str, ...]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return _DEFAULT_NUMBER_STEPS
    raw = extractor.get("normalization")
    if not isinstance(raw, list) or not raw:
        return _DEFAULT_NUMBER_STEPS
    steps = tuple(str(item) for item in raw)
    # Каталожный скелет пишет только nfc/collapse_spaces; без запятой
    # русские ТЭП ("5000,0") не разбираются. Не подменяем заданный порядок.
    extras = tuple(step for step in ("decimal_comma", "strip_unit") if step not in steps)
    return steps + extras


def _captured_number(match: re.Match[str]) -> str:
    """Первая непустая группа, иначе весь матч (альтернативы мм|м)."""

    for group in match.groups():
        if group:
            return group
    return match.group(0)


def _join(tokens: Sequence[PageToken]) -> str:
    return " ".join(item.text for item in tokens)


def _find_anchor_end(tokens: Sequence[PageToken], anchors: Sequence[str]) -> int | None:
    for start in range(len(tokens)):
        chunk: list[str] = []
        for end in range(start, min(len(tokens), start + _MAX_ANCHOR_TOKENS)):
            if tokens[end].page != tokens[start].page:
                break
            chunk.append(tokens[end].text)
            folded = fold_label(" ".join(chunk))
            if any(anchor in folded for anchor in anchors):
                return end
    return None


def _window(tokens: Sequence[PageToken], anchor_end: int) -> list[PageToken]:
    origin = tokens[anchor_end]
    rest = [
        item
        for item in tokens[anchor_end + 1 : anchor_end + 1 + _MAX_WINDOW_TOKENS]
        if item.page == origin.page
    ]
    same_row = [
        item for item in rest if y_overlap(origin.polygon_norm, item.polygon_norm)
    ]
    return same_row or rest


def parse_number_from_text(text: str, rule: dict[str, object]) -> float | None:
    """Первое число из произвольной строки тем же regex/normalization, что extract."""

    if not text.strip():
        return None
    matches = list(_regex(rule).finditer(text))
    if not matches:
        return None
    try:
        value = parse_number(_captured_number(matches[0]), _steps(rule))
    except ValueError:
        return None
    return scale_length_to_target(
        value,
        source_unit=length_unit_of_match(text, matches[0]),
        target_unit=_target_unit(rule),
    )


def _target_unit(rule: dict[str, object]) -> str | None:
    comparator = rule.get("comparator")
    if isinstance(comparator, dict):
        raw = comparator.get("unit_target")
        if isinstance(raw, str) and raw.strip():
            return raw
    unit = rule.get("unit")
    return unit if isinstance(unit, str) and unit.strip() else None


def extract_number(tokens: Sequence[PageToken], rule: dict[str, object]) -> NumberHit | None:
    """Найти число после якоря. Нет якоря или нет числа — None, не догадка."""

    if not tokens:
        return None
    ordered = _sorted(tokens)
    end = _find_anchor_end(ordered, _anchors(rule))
    if end is None:
        return None
    window = _window(ordered, end)
    if not window:
        return None
    text = _join(window)
    matches = list(_regex(rule).finditer(text))
    if not matches:
        return None
    steps = _steps(rule)
    target = _target_unit(rule)

    def _scaled(match: re.Match[str]) -> float:
        raw = _captured_number(match)
        value = parse_number(raw, steps)
        return scale_length_to_target(
            value,
            source_unit=length_unit_of_match(text, match),
            target_unit=target,
        )

    try:
        primary = _scaled(matches[0])
        secondary = _scaled(matches[-1])
    except ValueError:
        return None
    primary_raw = _captured_number(matches[0])
    covering = [item for item in window if item.text.strip()]
    source = union_rect_polygon(tuple(item.polygon_source for item in covering))
    norm = union_rect_polygon(tuple(item.polygon_norm for item in covering))
    agrees = primary == secondary
    return NumberHit(
        extraction=Extraction(
            raw_token=primary_raw,
            engine=engine_of(covering),
            engine_version=ENGINE_VERSION,
            confidence=0.99 if agrees else 0.4,
            normalized_value=primary,
            unit=str(rule["unit"]) if rule.get("unit") else None,
            grounded_in_source_tokens=True,
            second_read_agrees=agrees,
            confidence_features={
                "window_matches": float(len(matches)),
                "second_read": float(secondary),
            },
        ),
        page=ordered[end].page,
        polygon_source=source,
        polygon_norm=norm,
        window_text=text,
    )
