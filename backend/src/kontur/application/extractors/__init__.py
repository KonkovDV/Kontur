"""Экстракторы значений. Правило матрицы выбирает тип; код не знает 132 веток."""

from kontur.application.extractors.number import NumberHit, PageToken, extract_number
from kontur.application.extractors.text import TextHit, extract_text

__all__ = ["NumberHit", "PageToken", "TextHit", "extract_number", "extract_text"]
