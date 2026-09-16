"""Канонические коды параметров матрицы.

Организатор публикует трёхзначный формат (`PZ-001`, `AR-041`). В текстах
Приложения 2 и в черновиках репозитория встречаются короткие формы
(`PZ-01`, `AR-14`). Нормализация — на границе данных, не правка матрицы.

Код приходит из PDF, DOCX и XLSX через копипаст и OCR, поэтому перед разбором
снимается типографика: NFKC, неразрывные пробелы, неразрывный дефис, en/em dash,
минус U+2212, полноширинные символы. Кириллические префиксы разделов
(`ПЗ`, `СМ`, `ООС`) переводятся таблицей алиасов, а не побуквенной свёрткой:
иначе `СМ-132` стало бы `CM-132`, а `ООС-098` — `OOC-098`. Побуквенные
омоглифы (`РZ-001`) применяются только если результат есть среди известных
кодов матрицы — иначе находка получила бы чужой латинский идентификатор.

Без этой нормализации код `AR\u2011014` не совпадёт ни с одним из 132 правил, и
находка потеряется без единого сообщения об ошибке.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

_CODE = re.compile(r"^([A-ZА-ЯЁ0-9]+(?:-[A-ZА-ЯЁ0-9]+)*)-(\d+)$")
_ASCII_CODE = re.compile(r"^[A-Z0-9-]+$")

#: Дефисоподобные символы из выгрузок Приложений 1 и 2.
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2043\u2212\ufe58\ufe63\uff0d"

#: Пробелы и невидимые разделители, которые OCR вставляет внутрь кода.
_SPACES = " \t\n\r\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
_SPACES += "\u2008\u2009\u200a\u200b\u202f\u205f\u2060\u3000\ufeff"

#: Кириллические префиксы разделов → канон каталога. Длинные первыми.
_SECTION_ALIASES: tuple[tuple[str, str], ...] = (
    ("СПЗУ", "SPZU"),
    ("ИОС1", "IOS1"),
    ("ИОС2", "IOS2"),
    ("ИОС3", "IOS3"),
    ("ИОС4", "IOS4"),
    ("ИОС5", "IOS5"),
    ("ПОС", "POS"),
    ("ПОД", "POD"),
    ("ООС", "OOS"),
    ("ППМ", "PPM"),
    ("ОДИ", "ODI"),
    ("ПЗ", "PZ"),
    ("АР", "AR"),
    ("КР", "KR"),
    ("ЗУ", "ZU"),
    ("СМ", "SM"),
)

#: Кириллица, неотличимая от латиницы в смешанных кодах (`РZ-001`).
#: Буквы, похожие на цифры («З» и «3»), сюда не входят.
_HOMOGLYPHS = {
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "У": "Y",
    "Х": "X",
    "Ѕ": "S",
    "І": "I",
    "Ј": "J",
}

_DASH_TABLE = {ord(char): "-" for char in _DASHES}
_SPACE_TABLE = dict.fromkeys(ord(char) for char in _SPACES)
_HOMOGLYPH_TABLE = str.maketrans(_HOMOGLYPHS)

KnownCodes = Iterable[str] | Mapping[str, object] | None


def normalize_code_text(code: str) -> str:
    """Снять типографику: результат без пробелов, с ASCII-дефисами, в верхнем регистре."""

    text = unicodedata.normalize("NFKC", code)
    text = text.translate(_DASH_TABLE)
    text = text.translate(_SPACE_TABLE)
    return text.upper()


def fold_latin_homoglyphs(text: str) -> str:
    """Свернуть кириллические омоглифы, но только если код становится ASCII.

    `РZ-001` (русская «Р») → `PZ-001`. Настоящий кириллический код (`ЗУ-001`)
    остаётся как есть: «З» омоглифа не имеет, свёртка не даёт ASCII и отменяется.
    Побуквенно `СМ-132` стало бы `CM-132` — эту порчу отсекает
    `apply_section_alias` и проверка `known_codes`.
    """

    folded = text.translate(_HOMOGLYPH_TABLE)
    return folded if _ASCII_CODE.fullmatch(folded) else text


def apply_section_alias(text: str) -> str:
    """`ПЗ-001` / `СМ-132` / `ООС-098` → канон каталога, без побуквенной свёртки."""

    match = _CODE.fullmatch(text)
    if match is None:
        return text
    prefix, number = match.group(1), match.group(2)
    for cyrillic, latin in _SECTION_ALIASES:
        if prefix == cyrillic:
            return f"{latin}-{number}"
    return text


def _pad_number(text: str) -> str:
    match = _CODE.fullmatch(text)
    if match is None:
        return text
    return f"{match.group(1)}-{int(match.group(2)):03d}"


def _known_set(known_codes: KnownCodes) -> frozenset[str] | None:
    if known_codes is None:
        return None
    if isinstance(known_codes, Mapping):
        return frozenset(known_codes)
    return frozenset(known_codes)


def canonicalize_rule_code(code: str, known_codes: KnownCodes = None) -> str:
    """`AR-14` и `AR-041` — один код. Нематричные идентификаторы не отбрасываются.

    Если передан `known_codes`, побуквенная свёртка принимается только когда
    результат есть в матрице. Иначе `СМ-132` не превращается в несуществующий
    `CM-132`.
    """

    normalized = _pad_number(normalize_code_text(code))
    aliased = _pad_number(apply_section_alias(normalized))
    folded_raw = _pad_number(fold_latin_homoglyphs(normalized))
    folded_alias = _pad_number(fold_latin_homoglyphs(aliased))
    known = _known_set(known_codes)
    if known is not None:
        for item in (normalized, aliased, folded_raw, folded_alias):
            if item in known:
                return item
        return aliased
    return folded_alias


def display_alias(code: str) -> str:
    """Короткая форма из Приложения 2: `AR-014` → `AR-14`."""

    canonical = canonicalize_rule_code(code)
    match = _CODE.fullmatch(canonical)
    if match is None:
        return canonical
    return f"{match.group(1)}-{int(match.group(2))}"


def is_canonical_rule_code(code: str) -> bool:
    """Код уже канонический: ничего не потеряется при записи в матрицу или в submission."""

    return bool(_CODE.fullmatch(code)) and canonicalize_rule_code(code) == code
