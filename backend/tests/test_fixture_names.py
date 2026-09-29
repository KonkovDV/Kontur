"""Фикстуры не несут чужих ФИО из штампа.

Допустим учебный «Тестов». Список живых фамилий в git не кладётся.
"""

from __future__ import annotations

import re
from pathlib import Path

_FIO = re.compile(r"([А-ЯЁ][а-яё]{2,})\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.")
_ALLOWED = frozenset({"Тестов"})


def test_stamp_names_in_backend_tests_are_the_fixture() -> None:
    root = Path(__file__).resolve().parents[1]
    found: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "test_fixture_names.py":
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            for match in _FIO.finditer(line):
                surname = match.group(1)
                if surname not in _ALLOWED:
                    found.append(f"{path.name}:{line_no}:{surname}")
    assert found == []
