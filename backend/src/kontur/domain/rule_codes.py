"""Канонические коды параметров матрицы.

Организатор публикует трёхзначный формат (`PZ-001`, `AR-041`). В текстах
Приложения 2 и в черновиках репозитория встречаются короткие формы
(`PZ-01`, `AR-14`). Нормализация — на границе данных, не правка матрицы.
"""

from __future__ import annotations

import re

_CODE = re.compile(r"^([A-ZА-Я0-9]+(?:-[A-ZА-Я0-9]+)*)-(\d+)$")


def canonicalize_rule_code(code: str) -> str:
    """`AR-14` и `AR-041` — один код. Нематричные идентификаторы не отбрасываются."""

    text = code.strip().upper().replace(" ", "")
    match = _CODE.fullmatch(text)
    if match is None:
        return text
    return f"{match.group(1)}-{int(match.group(2)):03d}"


def display_alias(code: str) -> str:
    """Короткая форма из Приложения 2: `AR-014` → `AR-14`."""

    canonical = canonicalize_rule_code(code)
    match = _CODE.fullmatch(canonical)
    if match is None:
        return code
    return f"{match.group(1)}-{int(match.group(2))}"
