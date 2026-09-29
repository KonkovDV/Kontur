"""Нормализация извлечённых чисел. raw_token не перезаписывается."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

_UNIT_TAIL = re.compile(r"(?:м\u00b2|м2|m2|м\^2)\s*$", re.IGNORECASE)
_SPACES = re.compile(r"[\s\u00a0\u202f]+")
# После collapse_spaces/decimal_comma: «500×300» / «500x300» / «500х300».
_DIM_SEP = re.compile(r"^(\d+(?:\.\d+)?)[×xх](\d+(?:\.\d+)?)$")
_LENGTH_TO_METERS: dict[str, float] = {"мм": 0.001, "см": 0.01, "м": 1.0}

_ROUNDING = {
    "none": None,
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "floor": ROUND_FLOOR,
    "ceil": ROUND_CEILING,
}

QUANTUM = Decimal("0.0001")


def fold_label(text: str) -> str:
    """Сравнение подписей: регистр и м²/м2 не должны разводить якорь и ячейку."""

    folded = unicodedata.normalize("NFC", text).casefold()
    folded = folded.replace("м²", "м2").replace("m²", "m2")
    return _SPACES.sub(" ", folded).strip()


def normalize_key_field(value: str) -> str:
    """Exact Match шифра, редакции и листа: NFC и пробелы, без смены регистра."""

    return _SPACES.sub(" ", unicodedata.normalize("NFC", value)).strip()


def apply_number_normalizations(raw: str, steps: Sequence[str]) -> str:
    """Вернуть строку, готовую к float(). raw_token остаётся у вызывающего."""

    text = raw
    ordered = tuple(steps) if steps else ("nfc", "collapse_spaces", "decimal_comma")
    if "nfc" in ordered:
        text = unicodedata.normalize("NFC", text)
    if "strip_unit" in ordered:
        text = _UNIT_TAIL.sub("", text).strip()
    if "collapse_spaces" in ordered:
        text = _SPACES.sub("", text)
    else:
        text = text.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if "decimal_comma" in ordered:
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
    if "multiply_dimensions" in ordered:
        matched = _DIM_SEP.match(text)
        if matched is not None:
            area = float(matched.group(1)) * float(matched.group(2))
            text = str(int(area) if area == int(area) else area)
    if "upper" in ordered:
        text = text.upper()
    return text


def canonical_length_unit(label: str) -> str | None:
    """мм / см / м. Площадь и теплотехника не длина."""

    folded = fold_label(label).replace(" ", "")
    if folded in {"мм", "mm"}:
        return "мм"
    if folded in {"см", "cm"}:
        return "см"
    if folded in {"м", "m"}:
        return "м"
    return None


def length_unit_after(text: str, match_end: int) -> str | None:
    """Единица сразу после числа. Голое число не единица."""

    tail = fold_label(text[match_end : match_end + 12]).lstrip()
    if tail.startswith("мм") or tail.startswith("mm"):
        return "мм"
    if tail.startswith("см") or tail.startswith("cm"):
        return "см"
    if tail.startswith("м2") or tail.startswith("m2"):
        return None
    if tail.startswith("м") or tail.startswith("m"):
        return "м"
    return None


def length_unit_of_match(text: str, match: re.Match[str]) -> str | None:
    """Единица в самом матче или сразу после. Голое число не единица."""

    span = fold_label(match.group(0))
    if "мм" in span or span.endswith("mm"):
        return "мм"
    if "см" in span or span.endswith("cm"):
        return "см"
    after = length_unit_after(text, match.end())
    if after is not None:
        return after
    if span.endswith("м2") or span.endswith("m2"):
        return None
    if span.endswith("м") or span.endswith("m"):
        return "м"
    return None


def scale_length_to_target(
    value: float,
    *,
    source_unit: str | None,
    target_unit: str | None,
) -> float:
    """Перевод длины только когда обе единицы явные. Голый 1200 не мм."""

    source = canonical_length_unit(source_unit or "")
    target = canonical_length_unit(target_unit or "")
    if source is None or target is None or source == target:
        return value
    meters = value * _LENGTH_TO_METERS[source]
    return meters / _LENGTH_TO_METERS[target]


def parse_number(raw: str, steps: Sequence[str]) -> float:
    text = apply_number_normalizations(raw, steps)
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"не разбирается как число: {raw!r}") from exc


def quantize(value: float, rounding: str) -> Decimal:
    decimal = Decimal(str(value))
    mode = _ROUNDING.get(rounding, ROUND_HALF_UP)
    if mode is None:
        return decimal
    return decimal.quantize(QUANTUM, rounding=mode)
