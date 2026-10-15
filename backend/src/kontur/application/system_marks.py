"""Марки систем на чертеже: список и короткий диапазон.

«В2.7,8,9» — три марки, «В2.4-В2.6» — три марки подряд. Размер решётки
и голая буква в ведомость не попадают.
"""

from __future__ import annotations

import re

from kontur.application.room_compare import label_text

_LATIN = str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ")
_HEAD = r"(ПЕ|ВЕ|ПД|ДУ|П|В)"
_RANGE = re.compile(
    rf"^{_HEAD}(\d{{1,2}})\.(\d{{1,2}})\s*[-–]\s*(?:{_HEAD}(\d{{1,2}})\.)?(\d{{1,2}})$"
)
_LIST = re.compile(rf"^{_HEAD}(\d{{1,2}})\.(\d{{1,2}}(?:\s*,\s*\d{{1,2}})+)$")
_ONE = re.compile(rf"^{_HEAD}(\d{{1,2}}(?:\.\d{{1,2}})?)?$")


def expand_system_marks(text: str) -> tuple[str, ...]:
    """Разворачивает одну подпись в марки. Пустой кортеж — это не список систем."""

    folded = label_text(text).upper().translate(_LATIN)
    folded = re.sub(r"\s*([,–-])\s*", r"\1", folded)
    marks: list[str] = []
    for word in folded.split():
        for part in re.split(r"[/\\]", word.strip(" .:;,]|[()")):
            pieces = [piece for piece in part.split(",") if piece]
            if len(pieces) > 1 and all(_one(piece) for piece in pieces):
                for piece in pieces:
                    marks.extend(_one(piece))
                continue
            marks.extend(_one(part))
    return tuple(dict.fromkeys(marks))


def _one(part: str) -> tuple[str, ...]:
    if not part or "*" in part:
        return ()
    ranged = _RANGE.fullmatch(part)
    if ranged is not None:
        prefix, system, start, other_prefix, other_system, end = ranged.groups()
        if other_prefix is not None and (other_prefix != prefix or other_system != system):
            return ()
        left, right = int(start), int(end)
        if 0 < right - left <= 12:
            return tuple(f"{prefix}{system}.{index}" for index in range(left, right + 1))
        return ()
    listed = _LIST.fullmatch(part)
    if listed is not None:
        prefix, system, tail = listed.groups()
        return tuple(
            f"{prefix}{system}.{int(piece)}"
            for piece in re.split(r"\s*,\s*", tail)
        )
    single = _ONE.fullmatch(part)
    if single is None:
        return ()
    prefix, number = single.groups()
    if number is None:
        return (prefix,) if prefix in {"ВЕ", "ПЕ"} else ()
    if number.startswith("0") and "." not in number:
        return ()
    return (f"{prefix}{number}",)
