"""Нормализация извлечённых чисел. raw_token не перезаписывается."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

_UNIT_TAIL = re.compile(r"(?:м\u00b2|м2|m2|м\^2)\s*$", re.IGNORECASE)
_UNIT_BODY = re.compile(r"^[\d.,]+")
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
        text = _localize_decimal(text)
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


# Площадь и объём в СИ. Длина сюда не входит: мм и мм² — разные величины.
_MEASURE_TO_SI: dict[str, tuple[str, float]] = {
    "мм": ("length", 0.001),
    "см": ("length", 0.01),
    "м": ("length", 1.0),
    "мм2": ("area", 1e-6),
    "см2": ("area", 1e-4),
    "м2": ("area", 1.0),
    "мм3": ("volume", 1e-9),
    "см3": ("volume", 1e-6),
    "м3": ("volume", 1.0),
    "тыс.м2": ("area", 1000.0),
    "тыс.м3": ("volume", 1000.0),
    "Вт": ("power", 1.0),
    "кВт": ("power", 1_000.0),
    "МВт": ("power", 1_000_000.0),
    "Па": ("pressure", 1.0),
    "кПа": ("pressure", 1_000.0),
    "МПа": ("pressure", 1_000_000.0),
    "м3/ч": ("flow", 1.0 / 3600.0),
    "л/с": ("flow", 0.001),
    "м3/сут": ("flow", 1.0 / 86400.0),
    "%": ("ratio", 0.01),
    "‰": ("ratio", 0.001),
}
# Регистр приставки сохраняется: «МВт» не «мВт», «МПа» не «мПа».
_EXACT_UNITS: dict[str, str] = {
    "Вт": "Вт",
    "вт": "Вт",
    "W": "Вт",
    "w": "Вт",
    "кВт": "кВт",
    "квт": "кВт",
    "kW": "кВт",
    "kw": "кВт",
    "МВт": "МВт",
    "MW": "МВт",
    "Па": "Па",
    "па": "Па",
    "Pa": "Па",
    "кПа": "кПа",
    "кпа": "кПа",
    "kPa": "кПа",
    "МПа": "МПа",
    "MPa": "МПа",
    "м3/ч": "м3/ч",
    "м³/ч": "м3/ч",
    "М3/ч": "м3/ч",
    "М³/ч": "м3/ч",
    "m3/h": "м3/ч",
    "л/с": "л/с",
    "l/s": "л/с",
    "м3/сут": "м3/сут",
    "м³/сут": "м3/сут",
    "%": "%",
    "‰": "‰",
    "промилле": "‰",
    "кв.м": "м2",
    "кв.м2": "м2",
    "куб.м": "м3",
    "куб.м3": "м3",
    "тыс.м2": "тыс.м2",
    "тыс.м²": "тыс.м2",
    "тыс.м3": "тыс.м3",
    "тыс.м³": "тыс.м3",
    "тыс.куб.м": "тыс.м3",
    "тыс.кв.м": "тыс.м2",
}
_SKIP_IF_OTHER_DIMENSION = frozenset({"power", "pressure", "flow", "ratio"})
_MEASURE_ALIASES: dict[str, str] = {
    "mm": "мм",
    "cm": "см",
    "m": "м",
    "mm2": "мм2",
    "cm2": "см2",
    "m2": "м2",
    "mm3": "мм3",
    "cm3": "см3",
    "m3": "м3",
}
# Длинный префикс раньше короткого: мм2 не должен читаться как мм.
_UNIT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("мм3", "мм3"),
    ("mm3", "мм3"),
    ("см3", "см3"),
    ("cm3", "см3"),
    ("мм2", "мм2"),
    ("mm2", "мм2"),
    ("см2", "см2"),
    ("cm2", "см2"),
    ("м3", "м3"),
    ("m3", "м3"),
    ("м2", "м2"),
    ("m2", "м2"),
    ("мм", "мм"),
    ("mm", "мм"),
    ("см", "см"),
    ("cm", "см"),
    ("м", "м"),
    ("m", "м"),
)


def _fold_unit_token(text: str) -> str:
    folded = fold_label(text).replace("²", "2").replace("³", "3")
    return folded.replace(" ", "").strip(".,;:)")


def _keep_case_unit(text: str) -> str:
    """NFKC и индексы ²/³. Регистр не схлопывается: приставка М и м разная."""

    kept = unicodedata.normalize("NFKC", text).strip()
    kept = kept.replace("²", "2").replace("³", "3").replace(" ", "")
    return kept.strip(".,;:)")


def canonical_measure_unit(label: str) -> tuple[str, str] | None:
    """(размерность, канон). Неизвестная подпись и смесь «Ом / мм²» — не единица."""

    exact = _EXACT_UNITS.get(_keep_case_unit(label))
    if exact is not None:
        return _MEASURE_TO_SI[exact][0], exact
    token = _fold_unit_token(label)
    if "/" in token:
        return None
    canon = _MEASURE_ALIASES.get(token, token)
    entry = _MEASURE_TO_SI.get(canon)
    if entry is None:
        return None
    return entry[0], canon


def measure_dimensions_conflict(source_unit: str | None, target_unit: str | None) -> bool:
    """Мощность, давление, расход и доля не подставляются вместо другой величины.

    Длина и площадь здесь не спорят: «500×300 мм» при цели мм² остаётся числом.
    """

    source = canonical_measure_unit(source_unit or "")
    target = canonical_measure_unit(target_unit or "")
    if source is None or target is None or source[0] == target[0]:
        return False
    return source[0] in _SKIP_IF_OTHER_DIMENSION or target[0] in _SKIP_IF_OTHER_DIMENSION


def scale_measure_to_target(
    value: float,
    *,
    source_unit: str | None,
    target_unit: str | None,
) -> float:
    """Перевод внутри одной размерности. мм к мм² не приводится."""

    source = canonical_measure_unit(source_unit or "")
    target = canonical_measure_unit(target_unit or "")
    if source is None or target is None or source[0] != target[0] or source[1] == target[1]:
        return value
    si = value * _MEASURE_TO_SI[source[1]][1]
    return si / _MEASURE_TO_SI[target[1]][1]


def _is_thousand_word(word: str) -> bool:
    return _fold_unit_token(word).rstrip(".") in {"тыс", "тысяч"}


def _is_square_word(word: str) -> bool:
    return _fold_unit_token(word).rstrip(".") in {"кв"}


def _is_cube_word(word: str) -> bool:
    return _fold_unit_token(word).rstrip(".") in {"куб"}


def _unit_from_words(words: list[str]) -> str | None:
    """«тыс. м²», «кв. м» и «куб. м» — одна величина, не соседнее слово."""

    if not words:
        return None
    if _is_thousand_word(words[0]) and len(words) >= 2:
        base = _resolve_unit(words[1])
        if base == "м2":
            return "тыс.м2"
        if base == "м3":
            return "тыс.м3"
        return None
    if _is_square_word(words[0]) and len(words) >= 2 and _resolve_unit(words[1]) == "м":
        return "м2"
    if _is_cube_word(words[0]) and len(words) >= 2 and _resolve_unit(words[1]) == "м":
        return "м3"
    return _resolve_unit(words[0])


def measure_unit_of_match(text: str, match: re.Match[str]) -> str | None:
    """Единица в матче, сразу после числа или сразу перед ним. «марка» не метр."""

    span = _keep_case_unit(match.group(0))
    tail = _UNIT_BODY.sub("", span)
    found = _resolve_unit(tail) if tail else None
    if found is not None:
        return found
    after = _unit_from_words(text[match.end() :].split()[:3])
    if after is not None:
        return after
    before = text[: match.start()].split()
    if len(before) >= 2 and (
        _is_thousand_word(before[-2])
        or _is_square_word(before[-2])
        or _is_cube_word(before[-2])
    ):
        compound = _unit_from_words(before[-2:])
        if compound is not None:
            return compound
    if not before:
        return None
    return _resolve_unit(before[-1])


def _resolve_unit(raw: str) -> str | None:
    if not raw:
        return None
    exact = _EXACT_UNITS.get(_keep_case_unit(raw))
    if exact is not None:
        return exact
    folded = _fold_unit_token(raw)
    if "/" in folded:
        return None
    return _prefix_unit(folded)


def _prefix_unit(folded: str) -> str | None:
    for prefix, canon in _UNIT_PREFIXES:
        if folded == prefix or folded.startswith(prefix):
            rest = folded[len(prefix) :]
            if rest == "":
                return canon
            if rest[0].isalnum() or rest[0] == "/":
                continue
            return canon
    return None


def _valid_thousand_chunks(chunks: list[str]) -> bool:
    if not chunks or not chunks[0].isdigit() or not (1 <= len(chunks[0]) <= 3):
        return False
    return all(chunk.isdigit() and len(chunk) == 3 for chunk in chunks[1:])


def _localize_decimal(text: str) -> str:
    """Правый разделитель — дробь. «1.254» не угадывается: тысячи или дробь.

    «1,254.30» — 1254.30, «1.254,30» — то же. Одна запятая остаётся дробью:
    «1,254» — 1.254. «10.005» — дробь. «1.254.300» — группы по три.
    """

    if not text:
        return text
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot:
            thousands, decimal = ".", ","
        else:
            thousands, decimal = ",", "."
        integer, frac = text.rsplit(decimal, 1)
        if not frac.isdigit():
            raise ValueError(f"дробная часть не цифры: {text!r}")
        if thousands in integer:
            chunks = integer.split(thousands)
            if not _valid_thousand_chunks(chunks):
                raise ValueError(f"группы тысяч не по три цифры: {text!r}")
            digits = "".join(chunks)
        else:
            digits = integer
        if not digits.isdigit():
            raise ValueError(f"целая часть не число: {text!r}")
        return f"{digits}.{frac}"
    if last_dot != -1:
        if text.count(".") == 1:
            left, right = text.split(".", 1)
            if (
                left.isdigit()
                and right.isdigit()
                and not left.startswith("0")
                and len(left) == 1
                and len(right) == 3
            ):
                raise ValueError(f"неоднозначно, тысячи или дробь: {text!r}")
            return text
        chunks = text.split(".")
        if _valid_thousand_chunks(chunks):
            return "".join(chunks)
        raise ValueError(f"группы тысяч не по три цифры: {text!r}")
    if last_comma != -1:
        if text.count(",") == 1:
            return text.replace(",", ".")
        chunks = text.split(",")
        if _valid_thousand_chunks(chunks):
            return "".join(chunks)
        raise ValueError(f"группы тысяч не по три цифры: {text!r}")
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


def measured_delta(actual: float, expected: float) -> float:
    """Разность двух измерений. 0.8 и 0.9 дают -0.1, а не двоичный хвост."""

    difference = Decimal(str(actual)) - Decimal(str(expected))
    return float(difference)
