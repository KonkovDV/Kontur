"""Метрики приёмки (ТЗ п. 14.3).

Считаются по evidence_group, никогда по страницам или файлам. Точечная оценка
публикуется только вместе с размером выборки, coverage и 95% доверительным
интервалом. Порог считается достигнутым по нижней границе интервала; для FPR —
по верхней.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from kontur.application.normalize import normalize_key_field

#: Обязательные минимумы ТЗ. Это пороги приёмки, а не заявленный результат.
#: Гармоника P=0.90 и R=0.80 ≈ 0.847 < 0.85: точка на полу precision и recall
#: не проходит F1. Запас держим по precision, не по recall.
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
_AREA_EPS = 1e-18

Point = tuple[float, float]
Polygon = tuple[Point, ...]


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    low: float
    high: float
    n: int


def wilson(successes: int, n: int, z: float = 1.96) -> Interval:
    """Интервал Уильсона. При n = 0 возвращает вырожденный интервал [0;1]."""

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


def key_field_exact_match(gold: str, predicted: str | None) -> bool:
    """Exact Match поля паспорта. None и пустая строка — промах, не «похоже»."""

    if predicted is None or not predicted.strip():
        return False
    return normalize_key_field(gold) == normalize_key_field(predicted)


def key_field_exact_match_interval(
    pairs: list[tuple[str, str | None]],
) -> Interval:
    """Доля совпавших ключевых полей. Пустая выборка не подтверждает порог."""

    successes = sum(1 for gold, predicted in pairs if key_field_exact_match(gold, predicted))
    return wilson(successes, len(pairs))


def _open_ring(polygon: Polygon) -> Polygon:
    if len(polygon) >= 2 and polygon[0] == polygon[-1]:
        return polygon[:-1]
    return polygon


def _signed_area(polygon: Polygon) -> float:
    ring = _open_ring(polygon)
    n = len(ring)
    if n < 3:
        return 0.0
    return (
        sum(
            ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1]
            for i in range(n)
        )
        / 2.0
    )


def _polygon_area(polygon: Polygon) -> float:
    """Площадь по формуле Гаусса. Знак отбрасывается."""

    return abs(_signed_area(polygon))


def _oriented_ccw(polygon: Polygon) -> Polygon:
    ring = _open_ring(polygon)
    if _signed_area(ring) < 0:
        return tuple(reversed(ring))
    return ring


def _clip_by_halfplane(
    polygon: list[Point],
    edge_start: Point,
    edge_end: Point,
) -> list[Point]:
    """Одна итерация Sutherland–Hodgman: оставить левую полуплоскость ребра."""

    if not polygon:
        return []
    ex = edge_end[0] - edge_start[0]
    ey = edge_end[1] - edge_start[1]

    def _cross(point: Point) -> float:
        # Ребро × (точка − начало): >0 слева от направленного ребра (внутри CCW).
        return ex * (point[1] - edge_start[1]) - ey * (point[0] - edge_start[0])

    def _inside(point: Point) -> bool:
        return _cross(point) >= 0.0

    def _intersect(start: Point, end: Point) -> Point:
        da = _cross(start)
        db = _cross(end)
        denom = da - db
        if abs(denom) < _AREA_EPS:
            return start
        t = max(0.0, min(1.0, da / denom))
        return (start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1]))

    result: list[Point] = []
    for index, current in enumerate(polygon):
        previous = polygon[index - 1]
        if _inside(current):
            if not _inside(previous):
                result.append(_intersect(previous, current))
            result.append(current)
        elif _inside(previous):
            result.append(_intersect(previous, current))
    return result


def _intersect_polygons(subject: Polygon, clip: Polygon) -> Polygon:
    """Пересечение. Клип ориентирован CCW; вогнутый клип не гарантирован."""

    output: list[Point] = list(subject)
    clip_ring = _oriented_ccw(clip)
    if len(clip_ring) < 3:
        return ()
    for index, start in enumerate(clip_ring):
        if not output:
            return ()
        output = _clip_by_halfplane(output, start, clip_ring[(index + 1) % len(clip_ring)])
    return tuple(output)


def _finite_ring(polygon: Polygon) -> bool:
    return all(math.isfinite(x) and math.isfinite(y) for x, y in polygon)


def iou(poly_a: Polygon, poly_b: Polygon) -> float:
    """IoU нормализованных полигонов после CropBox/MediaBox/Rotate.

    Координаты — в [0;1], Y вниз, как в `domain/coordinates.py`. Вырожденные
    контуры (площадь 0) и неконечные координаты дают 0. Порог «локализовано» —
    `IOU_THRESHOLD`, не 0.95:
    0.95 — нижняя граница Wilson по доле пар, а не по одному IoU.
    """

    if not _finite_ring(poly_a) or not _finite_ring(poly_b):
        return 0.0
    left = _oriented_ccw(poly_a)
    right = _oriented_ccw(poly_b)
    area_a = _polygon_area(left)
    area_b = _polygon_area(right)
    if area_a <= _AREA_EPS or area_b <= _AREA_EPS:
        return 0.0
    area_inter = _polygon_area(_intersect_polygons(left, right))
    area_union = area_a + area_b - area_inter
    if area_union <= _AREA_EPS:
        return 0.0
    return max(0.0, min(1.0, area_inter / area_union))


def evidence_localization_interval(
    pairs: list[tuple[Polygon, Polygon]],
    threshold: float = IOU_THRESHOLD,
) -> Interval:
    """Доля пар с IoU ≥ threshold. Пустая выборка порог не подтверждает."""

    successes = sum(1 for gold, predicted in pairs if iou(gold, predicted) >= threshold)
    return wilson(successes, len(pairs))


def character_accuracy(reference: str, hypothesis: str) -> float:
    """1 − CER. Unicode NFC, схлопывание повторных пробелов.

    Регистр не сворачивается: шифры и редакции чувствительны к регистру
    (ТЗ п. 9.1). Не смешивать с Exact Match полей.
    """

    def _prepare(s: str) -> str:
        """NFC + схлопывание двойных пробелов + зачистка краёв."""
        return re.sub(r"  +", " ", unicodedata.normalize("NFC", s)).strip()

    ref = _prepare(reference)
    hyp = _prepare(hypothesis)

    # Быстрые пути
    if not ref and not hyp:
        return 1.0
    if not ref:
        # Пустой эталон при непустой гипотезе — CER не определён, возвращаем 0.
        return 0.0
    if ref == hyp:
        return 1.0

    # Wagner–Fischer Levenshtein, O(m·n) time, O(n) space
    m = len(ref)
    n_hyp = len(hyp)
    prev = list(range(n_hyp + 1))
    for i, rc in enumerate(ref, 1):
        curr = [i] + [0] * n_hyp
        for j, hc in enumerate(hyp, 1):
            if rc == hc:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr

    cer = prev[n_hyp] / m
    return max(0.0, 1.0 - cer)
