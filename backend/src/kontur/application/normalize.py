"""Нормализация извлечённых чисел. raw_token не перезаписывается."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

_UNIT_TAIL = re.compile(r"(?:м\u00b2|м2|m2|м\^2)\s*$", re.IGNORECASE)
_SPACES = re.compile(r"[\s\u00a0\u202f]+")

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
    if "upper" in ordered:
        text = text.upper()
    return text


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
