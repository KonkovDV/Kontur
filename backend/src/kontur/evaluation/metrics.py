"""Метрики приёмки (ТЗ п. 14.3).

Считаются по evidence_group, никогда по страницам или файлам. Точечная оценка
публикуется только вместе с размером выборки, coverage и 95% доверительным
интервалом. Порог считается достигнутым по нижней границе интервала; для FPR —
по верхней.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Обязательные минимумы ТЗ. Это пороги приёмки, а не заявленный результат.
TZ_THRESHOLDS: dict[str, float] = {
    "character_accuracy": 0.95,
    "key_field_exact_match": 0.90,
    "document_linkage": 0.95,
    "evidence_localization": 0.95,
    "precision": 0.90,
    "recall": 0.80,
    "f1": 0.85,
    "false_positive_rate": 0.10,  # верхняя граница
}

#: Внутренние цели команды. Выше порогов, чтобы просадка не ломала приёмку.
INTERNAL_TARGETS: dict[str, float] = {
    "character_accuracy": 0.98,
    "key_field_exact_match": 0.96,
    "document_linkage": 0.99,
    "evidence_localization": 0.99,
    "precision": 0.95,
    "recall": 0.88,
    "f1": 0.91,
    "false_positive_rate": 0.05,
}

IOU_THRESHOLD = 0.50


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    low: float
    high: float
    n: int


def wilson(successes: int, n: int, z: float = 1.96) -> Interval:
    """Интервал Уилсона. При n = 0 возвращает вырожденный интервал [0;1]."""

    if n <= 0:
        return Interval(point=0.0, low=0.0, high=1.0, n=0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return Interval(point=p, low=max(0.0, centre - spread), high=min(1.0, centre + spread), n=n)


def meets_threshold(name: str, interval: Interval) -> bool:
    """Проверка порога по консервативной границе интервала."""

    threshold = TZ_THRESHOLDS[name]
    if name == "false_positive_rate":
        return interval.high <= threshold
    return interval.low >= threshold


def f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def iou(poly_a: object, poly_b: object) -> float:
    """IoU нормализованных полигонов после учёта CropBox и Rotate."""

    raise NotImplementedError("L3: считается на нормализованной геометрии страницы")


def character_accuracy(reference: str, hypothesis: str) -> float:
    """1 − CER. Unicode NFC, схлопывание повторных пробелов.

    Регистр игнорируется только там, где он не несёт смысла; знаки в шифрах и
    редакциях не удаляются (ТЗ п. 9.1).
    """

    raise NotImplementedError("E1")
