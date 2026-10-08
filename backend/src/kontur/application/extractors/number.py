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
from kontur.domain.geometry import reading_key, y_overlap
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


_STANDARD = re.compile(r"(сп|снип|гост)\s*(\d+(?:[.\-]\d+)*)", re.IGNORECASE)
_ROW_PREFIX = re.compile(r"^\d{1,2}\.$")


def _anchor_spans(
    tokens: Sequence[PageToken], anchors: Sequence[str]
) -> tuple[tuple[int, int], ...]:
    """Все вхождения якоря, не первое. Пустая страница якорей не получает."""

    spans: list[tuple[int, int]] = []
    for start in range(len(tokens)):
        chunk: list[str] = []
        for end in range(start, min(len(tokens), start + _MAX_ANCHOR_TOKENS)):
            if tokens[end].page != tokens[start].page:
                break
            chunk.append(tokens[end].text)
            folded = fold_label(" ".join(chunk))
            if any(anchor in folded for anchor in anchors):
                spans.append((start, end))
                break
    return tuple(spans)


def _find_anchor_end(tokens: Sequence[PageToken], anchors: Sequence[str]) -> int | None:
    spans = _anchor_spans(tokens, anchors)
    if not spans:
        return None
    return spans[0][1]


def _standards(text: str) -> set[tuple[str, str]]:
    return {
        (kind.casefold(), number.replace("-", "."))
        for kind, number in _STANDARD.findall(fold_label(text))
    }


def _rule_standards(rule: dict[str, object]) -> set[tuple[str, str]]:
    raw = rule.get("normative_refs")
    if not isinstance(raw, list):
        return set()
    parts: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            parts.append(str(item.get("identifier") or ""))
            parts.append(str(item.get("clause") or ""))
        elif isinstance(item, str):
            parts.append(item)
    return _standards(" ".join(parts))


def _norm_mismatch(window_text: str, rule: dict[str, object]) -> bool:
    """Чужой СП/ГОСТ/СНиП понижает окно. Пустой перечень правила ничего не режет."""

    expected = _rule_standards(rule)
    cited = _standards(window_text)
    if not expected or not cited:
        return False
    return expected.isdisjoint(cited)


def _numbered_row(tokens: Sequence[PageToken], start: int) -> bool:
    if start <= 0:
        return False
    prefix = tokens[start - 1]
    anchor = tokens[start]
    if prefix.page != anchor.page:
        return False
    if not y_overlap(prefix.polygon_norm, anchor.polygon_norm):
        return False
    return _ROW_PREFIX.fullmatch(prefix.text.strip()) is not None


def _match_token_index(window: Sequence[PageToken], match: re.Match[str]) -> int:
    cursor = 0
    for index, token in enumerate(window):
        start = cursor
        cursor += len(token.text)
        if start <= match.start() < cursor:
            return index
        cursor += 1
    return len(window)


@dataclass(frozen=True, slots=True)
class _Read:
    value: float
    raw: str
    token: PageToken
    note: bool
    distance: int


def _note_flags(tokens: Sequence[PageToken]) -> tuple[bool, ...]:
    """Число внутри скобок — примечание строки, не ячейка."""

    depth = 0
    flags: list[bool] = []
    for token in tokens:
        flags.append(depth > 0 or "(" in token.text)
        depth = max(0, depth + token.text.count("(") - token.text.count(")"))
    return tuple(flags)


def _reads(
    tokens: Sequence[PageToken], rule: dict[str, object], *, nearest_at_end: bool
) -> list[_Read]:
    if not tokens:
        return []
    flags = _note_flags(tokens)
    text = _join(tokens)
    steps = _steps(rule)
    target = _target_unit(rule)
    found: list[_Read] = []
    last = len(tokens) - 1
    for match in _regex(rule).finditer(text):
        local = _match_token_index(tokens, match)
        if local >= len(tokens):
            continue
        token = tokens[local]
        if _ROW_PREFIX.fullmatch(token.text.strip()):
            continue
        try:
            raw = _captured_number(match)
            value = scale_length_to_target(
                parse_number(raw, steps),
                source_unit=length_unit_of_match(text, match),
                target_unit=target,
            )
        except ValueError:
            continue
        distance = last - local if nearest_at_end else local
        found.append(
            _Read(value=value, raw=raw, token=token, note=flags[local], distance=distance)
        )
    return found


def _same_row(
    ordered: Sequence[PageToken], start: int, end: int
) -> tuple[list[PageToken], list[PageToken]]:
    origin = ordered[end]
    before: list[PageToken] = []
    after: list[PageToken] = []
    for index, token in enumerate(ordered):
        if token.page != origin.page or not y_overlap(origin.polygon_norm, token.polygon_norm):
            continue
        if start <= index <= end:
            continue
        if index < start:
            before.append(token)
        else:
            after.append(token)
    return before, after


def _forward_rest(ordered: Sequence[PageToken], end: int) -> list[PageToken]:
    """Следующие строки, когда в строке якоря справа пусто. Не дальше окна."""

    origin = ordered[end]
    rest: list[PageToken] = []
    for token in ordered[end + 1 : end + 1 + _MAX_WINDOW_TOKENS]:
        if token.page != origin.page:
            break
        if y_overlap(origin.polygon_norm, token.polygon_norm):
            continue
        rest.append(token)
    return rest


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


def _candidate_from_span(
    ordered: Sequence[PageToken],
    start: int,
    end: int,
    rule: dict[str, object],
) -> tuple[tuple[int, int, int, int, int, int, int], NumberHit] | None:
    """Число строки. Слева от подписи — ячейка, в скобках справа — примечание.

    Первое и последнее чтение считаются только по ячейкам. Примечание не
    спорит с ячейкой и не заставляет отказ. Нет числа — None, не догадка.
    """

    before, after = _same_row(ordered, start, end)
    real_after = [item for item in _reads(after, rule, nearest_at_end=False) if not item.note]
    real_before = [item for item in _reads(before, rule, nearest_at_end=True) if not item.note]
    notes = [item for item in _reads(after, rule, nearest_at_end=False) if item.note]
    note_only = False
    if real_after:
        chosen = real_after
        context = before + after
    elif real_before:
        chosen = [min(real_before, key=lambda item: (item.distance, item.raw))]
        context = before + after
    elif notes:
        chosen = notes
        note_only = True
        context = before + after
    elif not after:
        rest = _forward_rest(ordered, end)
        chosen = _reads(rest, rule, nearest_at_end=False)
        context = rest
    else:
        return None
    if not chosen:
        return None
    primary = chosen[0]
    secondary = chosen[-1]
    origin = ordered[end]
    agrees = primary.value == secondary.value
    same_row = y_overlap(origin.polygon_norm, primary.token.polygon_norm)
    text = _join(context)
    hit = NumberHit(
        extraction=Extraction(
            raw_token=primary.raw,
            engine=engine_of((primary.token,)),
            engine_version=ENGINE_VERSION,
            confidence=0.99 if agrees else 0.4,
            normalized_value=primary.value,
            unit=str(rule["unit"]) if rule.get("unit") else None,
            grounded_in_source_tokens=True,
            second_read_agrees=agrees,
            confidence_features={
                "window_matches": float(len(chosen)),
                "second_read": float(secondary.value),
            },
        ),
        page=origin.page,
        polygon_source=primary.token.polygon_source,
        polygon_norm=primary.token.polygon_norm,
        window_text=text,
    )
    rank = (
        0 if same_row else 1,
        1 if note_only else 0,
        1 if _norm_mismatch(text, rule) else 0,
        1 if primary.value == 0.0 else 0,
        primary.distance,
        0 if _numbered_row(ordered, start) else 1,
        end,
    )
    return rank, hit


def extract_number(tokens: Sequence[PageToken], rule: dict[str, object]) -> NumberHit | None:
    """Число у самого плотного якоря.

    Первое совпадение в порядке чтения не выигрывает, если дальше по листу
    есть число в той же строке, ненулевой шаблон или норматив правила.
    Число слева от подписи берётся, когда справа только скобочное примечание.
    Ноль остаётся, когда другого числа нет. Нет якоря или нет числа — None.
    """

    if not tokens:
        return None
    ordered = _sorted(tokens)
    spans = _anchor_spans(ordered, _anchors(rule))
    if not spans:
        return None
    chosen: tuple[tuple[int, int, int, int, int, int, int], NumberHit] | None = None
    for start, end in spans:
        candidate = _candidate_from_span(ordered, start, end, rule)
        if candidate is None:
            continue
        if chosen is None or candidate[0] < chosen[0]:
            chosen = candidate
    if chosen is None:
        return None
    return chosen[1]
