"""Согласие текстового слоя PDF с тем, что видно на растре (RT-B).

Текстовый слой может содержать белый, перекрытый или render-mode=invisible
текст внутри CropBox. Такой фрагмент нельзя брать в паспорт и в находку.
None — детектор не чем измерить (нет текста или слишком мелкий бокс).
True ставится только после выборки пикселей, не «потому что токены есть».
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

#: СКО яркости 0–255. Ниже — пятно однородное, букв на растре нет.
MIN_VISIBLE_STD = 8.0
_MIN_SAMPLES = 16

GraySamples = Sequence[float]


@dataclass(frozen=True, slots=True)
class VisualTextAssessment:
    agreement: bool | None
    sampled_tokens: int
    hidden_tokens: int
    inconclusive_tokens: int


def gray_std(samples: GraySamples) -> float:
    values = list(samples)
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((item - mean) ** 2 for item in values) / len(values)
    return math.sqrt(variance)


def token_is_visually_present(text: str, samples: GraySamples) -> bool | None:
    """None — мало пикселей, не гадаем. False — текст есть, растр пустой."""

    if not text.strip():
        return True
    if len(samples) < _MIN_SAMPLES:
        return None
    return gray_std(samples) >= MIN_VISIBLE_STD


def agree_visual_and_text(flags: Sequence[bool | None]) -> VisualTextAssessment:
    """Хотя бы один скрытый токен → False. Нет измерений → None."""

    known = [flag for flag in flags if flag is not None]
    hidden = sum(1 for flag in known if flag is False)
    inconclusive = sum(1 for flag in flags if flag is None)
    sampled = len(flags)
    if not known:
        agreement: bool | None = None
    elif hidden:
        agreement = False
    else:
        agreement = True
    return VisualTextAssessment(
        agreement=agreement,
        sampled_tokens=sampled,
        hidden_tokens=hidden,
        inconclusive_tokens=inconclusive,
    )
