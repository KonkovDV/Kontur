"""Масштаб листа из основной надписи.

Ищем «М 1:N» или «1:N» только в нижней полосе штампа. Нет подписи —
масштаб неизвестен, сечение в миллиметры не переводим.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from kontur.application.extractors.number import PageToken

STAMP_Y = 0.85
_SCALE = re.compile(r"(?:м\s*)?1\s*:\s*(\d{2,4})", re.IGNORECASE)


def scale_mark(
    tokens: Sequence[PageToken], *, stamp_y: float = STAMP_Y
) -> tuple[int, int] | None:
    """Страница и знаменатель. None — в штампе нет читаемой подписи 1:N."""

    by_page: dict[int, list[str]] = {}
    for token in tokens:
        ys = [point[1] for point in token.polygon_norm]
        if not ys or min(ys) < stamp_y:
            continue
        by_page.setdefault(token.page, []).append(token.text)
    for page in sorted(by_page):
        match = _SCALE.search(" ".join(by_page[page]))
        if match is None:
            continue
        value = int(match.group(1))
        if value >= 1:
            return page, value
    return None


def scale_denominator(tokens: Sequence[PageToken], *, stamp_y: float = STAMP_Y) -> int | None:
    """Знаменатель масштаба. None — в штампе нет читаемой подписи 1:N."""

    mark = scale_mark(tokens, stamp_y=stamp_y)
    if mark is None:
        return None
    return mark[1]
