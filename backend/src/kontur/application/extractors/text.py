"""Извлечение текстового / enum значения у якоря из токенов страницы.

Аналог number.py для extractor.type=enum / text_regex.
Двойное чтение — два независимых прохода regex по одному окну:
первый матч (primary) и последний (secondary). Совпадают — second_read_agrees=True;
расходятся — ABSTAIN на уровне правила при dual_read_required=True.

Если extractor.regex = null, extract_text() возвращает None (не выбрасывает),
что приводит к LOW_QUALITY в evaluate_rule — безопасное отказное преобразование.

Поддерживаемые семейства:
  enum/text_regex : значение по регулярному выражению
  exact_field     : точное текстовое поле с обязательным value-regex
  presence        : наличие якоря; отсутствие не является нарушением
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from kontur.application.extractors.number import PageToken, engine_of
from kontur.application.normalize import fold_label
from kontur.domain.geometry import reading_key, union_rect_polygon, y_overlap
from kontur.domain.models import Extraction, Polygon

ENGINE_VERSION = "0.1.0"
_MAX_ANCHOR_TOKENS = 8
_MAX_WINDOW_TOKENS = 12


@dataclass(frozen=True, slots=True)
class TextHit:
    """Найденное текстовое/enum значение с привязкой к исходным токенам."""

    extraction: Extraction
    page: int
    polygon_source: Polygon
    polygon_norm: Polygon
    window_text: str


# ── вспомогательные функции (параллельны number.py) ──────────────────────────

def _sorted_tokens(tokens: Sequence[PageToken]) -> list[PageToken]:
    return sorted(tokens, key=lambda t: reading_key(t.page, t.polygon_norm))


def _join(tokens: Sequence[PageToken]) -> str:
    return " ".join(t.text for t in tokens)


def _find_anchor_end(tokens: Sequence[PageToken], anchors: Sequence[str]) -> int | None:
    """Найти индекс последнего токена совпавшего якоря."""
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
    """Токены после якоря на той же строке (y-overlap)."""
    origin = tokens[anchor_end]
    rest = [
        t for t in tokens[anchor_end + 1 : anchor_end + 1 + _MAX_WINDOW_TOKENS]
        if t.page == origin.page
    ]
    same_row = [t for t in rest if y_overlap(origin.polygon_norm, t.polygon_norm)]
    return same_row or rest


# ── извлечение параметров из правила ─────────────────────────────────────────

def _anchors_from_rule(rule: dict[str, object]) -> tuple[str, ...]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        raise TypeError("у правила нет extractor")
    raw = extractor.get("anchors")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{rule.get('code')}: нет якорей извлечения")
    return tuple(fold_label(str(a)) for a in raw)


def _regex_from_rule(rule: dict[str, object]) -> re.Pattern[str] | None:
    """Вернуть None (не выбрасывать!) если regex отсутствует или null.

    None → extract_text() возвращает None → LOW_QUALITY в evaluate_rule.
    Это безопасная обработка некорректно настроенных правил.
    """
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return None
    pattern = extractor.get("regex")
    if not isinstance(pattern, str) or not pattern:
        return None  # null или отсутствует — возвращаем None, не ValueError
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def _norm_steps(rule: dict[str, object]) -> tuple[str, ...]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return ("nfc", "collapse_spaces", "upper")
    raw = extractor.get("normalization")
    if not isinstance(raw, list) or not raw:
        return ("nfc", "collapse_spaces", "upper")
    return tuple(str(s) for s in raw)


def _normalize(value: str, steps: tuple[str, ...]) -> str:
    """Применить шаги нормализации. Всегда убирает крайние пробелы.

    Дополнительно схлопывает пробел между буквенным префиксом и цифрой:
    "B 25" → "B25", "R 60" → "R60", "C 0" → "C0".
    """
    result = value
    for step in steps:
        if step == "nfc":
            result = unicodedata.normalize("NFC", result)
        elif step == "upper":
            result = result.upper()
        elif step == "lower":
            result = result.lower()
        elif step == "collapse_spaces":
            result = " ".join(result.split())
    result = result.strip()
    # Compact "B 25" → "B25", "C 0" → "C0", "A +" → "A+"
    result = re.sub(r"^([A-ZА-ЯЁ]+)\s+([0-9+])", r"\1\2", result)
    return result


# ── семейные экстракторы ────────────────────────────────────────────────────────

def _anchor_bounds(
    tokens: Sequence[PageToken], anchors: Sequence[str]
) -> tuple[int, int] | None:
    """Вернуть границы якоря, не угадывая значение поля."""

    for start in range(len(tokens)):
        chunk: list[str] = []
        for end in range(start, min(len(tokens), start + _MAX_ANCHOR_TOKENS)):
            if tokens[end].page != tokens[start].page:
                break
            chunk.append(tokens[end].text)
            folded = fold_label(" ".join(chunk))
            if any(anchor in folded for anchor in anchors):
                return start, end
    return None


def _hit(
    *,
    tokens: Sequence[PageToken],
    extraction: Extraction,
    page: int,
    window_text: str,
) -> TextHit:
    """Создать hit с polygon только по реально прочитанным токенам."""

    covering = [item for item in tokens if item.text.strip()]
    if not covering:
        raise ValueError("evidence window is empty")
    return TextHit(
        extraction=extraction,
        page=page,
        polygon_source=union_rect_polygon(
            tuple(item.polygon_source for item in covering)
        ),
        polygon_norm=union_rect_polygon(
            tuple(item.polygon_norm for item in covering)
        ),
        window_text=window_text,
    )


def extract_exact_field(
    tokens: Sequence[PageToken], rule: dict[str, object]
) -> TextHit | None:
    """Извлечь точное текстовое поле после якоря.

    Поле обязано иметь extractor.regex/value_regex. Без явного шаблона
    экстрактор не угадывает границы многочастного значения и возвращает None;
    evaluate_rule переводит это в LOW_QUALITY.
    """

    if not tokens:
        return None
    pattern = _regex_from_rule(rule)
    if pattern is None:
        extractor = rule.get("extractor")
        if isinstance(extractor, dict):
            raw = extractor.get("value_regex")
            if isinstance(raw, str) and raw:
                pattern = re.compile(raw, re.IGNORECASE | re.UNICODE)
    if pattern is None:
        return None
    ordered = _sorted_tokens(tokens)
    bounds = _anchor_bounds(ordered, _anchors_from_rule(rule))
    if bounds is None:
        return None
    _start, end = bounds
    window = _window(ordered, end)
    if not window:
        return None
    text = _join(window)
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    steps = _norm_steps(rule)
    primary = _normalize(matches[0].group(0), steps)
    secondary = _normalize(matches[-1].group(0), steps)
    agrees = primary == secondary
    return _hit(
        tokens=window,
        extraction=Extraction(
            raw_token=matches[0].group(0),
            engine=engine_of(window),
            engine_version=ENGINE_VERSION,
            confidence=0.99 if agrees else 0.40,
            normalized_value=primary,
            grounded_in_source_tokens=True,
            second_read_agrees=agrees,
            confidence_features={
                "window_matches": float(len(matches)),
                "second_read_match": 1.0 if agrees else 0.0,
            },
        ),
        page=ordered[end].page,
        window_text=text,
    )


def extract_presence(
    tokens: Sequence[PageToken], rule: dict[str, object]
) -> TextHit | None:
    """Подтвердить наличие якоря. Отсутствие возвращает None, не CANDIDATE."""

    if not tokens:
        return None
    ordered = _sorted_tokens(tokens)
    bounds = _anchor_bounds(ordered, _anchors_from_rule(rule))
    if bounds is None:
        return None
    start, end = bounds
    anchor_tokens = ordered[start : end + 1]
    return _hit(
        tokens=anchor_tokens,
        extraction=Extraction(
            raw_token=_join(anchor_tokens),
            engine=engine_of(anchor_tokens),
            engine_version=ENGINE_VERSION,
            confidence=0.99,
            normalized_value=True,
            grounded_in_source_tokens=True,
            second_read_agrees=True,
            confidence_features={"presence": 1.0},
        ),
        page=ordered[end].page,
        window_text=_join(anchor_tokens),
    )


# ── публичное API ─────────────────────────────────────────────────────────────

def extract_text(
    tokens: Sequence[PageToken], rule: dict[str, object]
) -> TextHit | None:
    """Найти текстовое/enum значение после якоря. None — не догадка.

    Двойное чтение: первый regex-матч в окне (primary) и последний (secondary).
    Совпадают → second_read_agrees=True; расходятся → False.
    Если extractor.regex=null, возвращает None → evaluate_rule выдаст LOW_QUALITY.
    """
    if not tokens:
        return None
    pattern = _regex_from_rule(rule)  # None если regex=null
    if pattern is None:
        return None  # Безопасное отсутствие регулярного выражения
    ordered = _sorted_tokens(tokens)
    end = _find_anchor_end(ordered, _anchors_from_rule(rule))
    if end is None:
        return None
    window = _window(ordered, end)
    if not window:
        return None
    text = _join(window)
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    steps = _norm_steps(rule)
    primary_raw = matches[0].group(0)
    secondary_raw = matches[-1].group(0)
    primary_value = _normalize(primary_raw, steps)
    secondary_value = _normalize(secondary_raw, steps)
    agrees = primary_value == secondary_value
    covering = [t for t in window if t.text.strip()]
    source = union_rect_polygon(tuple(t.polygon_source for t in covering))
    norm = union_rect_polygon(tuple(t.polygon_norm for t in covering))
    return TextHit(
        extraction=Extraction(
            raw_token=primary_raw,
            engine=engine_of(covering),
            engine_version=ENGINE_VERSION,
            confidence=0.99 if agrees else 0.40,
            normalized_value=primary_value,
            unit=None,
            grounded_in_source_tokens=True,
            second_read_agrees=agrees,
            confidence_features={
                "window_matches": float(len(matches)),
                "second_read_match": 1.0 if agrees else 0.0,
            },
        ),
        page=ordered[end].page,
        polygon_source=source,
        polygon_norm=norm,
        window_text=text,
    )

