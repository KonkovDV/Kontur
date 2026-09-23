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


def scale_denominator(tokens: Sequence[PageToken], *, stamp_y: float = STAMP_Y) -> int | None:
    """Знаменатель масштаба. None — в штампе нет читаемой подписи 1:N."""

    parts: list[str] = []
    for token in tokens:
        ys = [point[1] for point in token.polygon_norm]
        if not ys or min(ys) < stamp_y:
            continue
        parts.append(token.text)
    if not parts:
        return None
    match = _SCALE.search(" ".join(parts))
    if match is None:
        return None
    value = int(match.group(1))
    if value < 1:
        return None
    return value
