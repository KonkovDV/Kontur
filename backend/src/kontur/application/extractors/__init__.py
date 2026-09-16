"""Экстракторы значений. Правило матрицы выбирает тип; код не знает 132 веток."""

from kontur.application.extractors.number import NumberHit, PageToken, extract_number

__all__ = ["NumberHit", "PageToken", "extract_number"]
