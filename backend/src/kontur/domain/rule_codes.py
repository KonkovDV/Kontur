"""Канонические коды параметров матрицы.

Организатор публикует трёхзначный формат (`PZ-001`, `AR-041`). В текстах
Приложения 2 и в черновиках репозитория встречаются короткие формы
(`PZ-01`, `AR-14`). Нормализация — на границе данных, не правка матрицы.

Код приходит из PDF, DOCX и XLSX через копипаст и OCR, поэтому перед разбором
снимается типографика: NFKC, неразрывные пробелы, неразрывный дефис, en/em dash,
минус U+2212, полноширинные символы. Отдельно складываются кириллические
омоглифы (`РZ-001` с русской «Р»): префиксы матрицы — латиница, и молчаливое
несовпадение такого кода стоит дороже, чем строгость свёртки.

Без этой нормализации код `AR\u2011014` не совпадёт ни с одним из 132 правил, и
находка потеряется без единого сообщения об ошибке.
"""

from __future__ import annotations

import re
import unicodedata

_CODE = re.compile(r"^([A-ZА-ЯЁ0-9]+(?:-[A-ZА-ЯЁ0-9]+)*)-(\d+)$")
_ASCII_CODE = re.compile(r"^[A-Z0-9-]+$")

#: Дефисоподобные символы из выгрузок Приложений 1 и 2.
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2043\u2212\ufe58\ufe63\uff0d"

#: Пробелы и невидимые разделители, которые OCR вставляет внутрь кода.
_SPACES = " \t\n\r\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
_SPACES += "\u2008\u2009\u200a\u200b\u202f\u205f\u2060\u3000\ufeff"

#: Кириллица, неотличимая от латиницы в кодах разделов (ТЗ Приложение 1).
#: Буквы, похожие на цифры («З» и «3»), сюда не входят: свёртка «ЗУ-001»
#: в «3Y-001» испортила бы настоящий код раздела.
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


def normalize_code_text(code: str) -> str:
    """Снять типографику: результат без пробелов, с ASCII-дефисами, в верхнем регистре."""

    text = unicodedata.normalize("NFKC", code)
    text = text.translate(_DASH_TABLE)
    text = text.translate(_SPACE_TABLE)
    return text.upper()


def fold_latin_homoglyphs(text: str) -> str:
    """Свернуть кириллические омоглифы, но только если код становится ASCII.

    `РZ-001` (русская «Р») → `PZ-001`. Настоящий кириллический код (`ПЗ-001`)
    остаётся как есть: «П» омоглифа не имеет, свёртка не даёт ASCII и отменяется.
    Так нормализация не переписывает коды, которых нет в латинской матрице.
    """

    folded = text.translate(_HOMOGLYPH_TABLE)
    return folded if _ASCII_CODE.fullmatch(folded) else text


def canonicalize_rule_code(code: str) -> str:
    """`AR-14` и `AR-041` — один код. Нематричные идентификаторы не отбрасываются."""

    text = fold_latin_homoglyphs(normalize_code_text(code))
    match = _CODE.fullmatch(text)
    if match is None:
        return text
    return f"{match.group(1)}-{int(match.group(2)):03d}"


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
