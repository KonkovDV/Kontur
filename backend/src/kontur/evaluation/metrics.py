"""\u041c\u0435\u0442\u0440\u0438\u043a\u0438 \u043f\u0440\u0438\u0451\u043c\u043a\u0438 (\u0422\u0417 \u043f. 14.3).\n\n\u0421\u0447\u0438\u0442\u0430\u044e\u0442\u0441\u044f \u043f\u043e evidence_group, \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043f\u043e \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430\u043c \u0438\u043b\u0438 \u0444\u0430\u0439\u043b\u0430\u043c. \u0422\u043e\u0447\u0435\u0447\u043d\u0430\u044f \u043e\u0446\u0435\u043d\u043a\u0430\n\u043f\u0443\u0431\u043b\u0438\u043a\u0443\u0435\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0432\u043c\u0435\u0441\u0442\u0435 \u0441 \u0440\u0430\u0437\u043c\u0435\u0440\u043e\u043c \u0432\u044b\u0431\u043e\u0440\u043a\u0438, coverage \u0438 95% \u0434\u043e\u0432\u0435\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u043c\n\u0438\u043d\u0442\u0435\u0440\u0432\u0430\u043b\u043e\u043c. \u041f\u043e\u0440\u043e\u0433 \u0441\u0447\u0438\u0442\u0430\u0435\u0442\u0441\u044f \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442\u044b\u043c \u043f\u043e \u043d\u0438\u0436\u043d\u0435\u0439 \u0433\u0440\u0430\u043d\u0438\u0446\u0435 \u0438\u043d\u0442\u0435\u0440\u0432\u0430\u043b\u0430; \u0434\u043b\u044f FPR \u2014\n\u043f\u043e \u0432\u0435\u0440\u0445\u043d\u0435\u0439.\n"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from kontur.application.normalize import normalize_key_field

#: \u041e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u044c\u043d\u044b\u0435 \u043c\u0438\u043d\u0438\u043c\u0443\u043c\u044b \u0422\u0417. \u042d\u0442\u043e \u043f\u043e\u0440\u043e\u0433\u0438 \u043f\u0440\u0438\u0451\u043c\u043a\u0438, \u0430 \u043d\u0435 \u0437\u0430\u044f\u0432\u043b\u0435\u043d\u043d\u044b\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442.
#: \u0413\u0430\u0440\u043c\u043e\u043d\u0438\u043a\u0430 P=0.90 \u0438 R=0.80 \u2248 0.847 < 0.85: \u0442\u043e\u0447\u043a\u0430 \u043d\u0430 \u043f\u043e\u043b\u0443 precision \u0438 recall
#: \u043d\u0435 \u043f\u0440\u043e\u0445\u043e\u0434\u0438\u0442 F1. \u0417\u0430\u043f\u0430\u0441 \u0434\u0435\u0440\u0436\u0438\u043c \u043f\u043e precision, \u043d\u0435 \u043f\u043e recall.
TZ_THRESHOLDS: dict[str, float] = {
    "character_accuracy": 0.95,
    "key_field_exact_match": 0.90,
    "document_linkage": 0.95,
    "evidence_localization": 0.95,
    "precision": 0.90,
    "recall": 0.80,
    "f1": 0.85,
    "false_positive_rate": 0.10,  # \u0432\u0435\u0440\u0445\u043d\u044f\u044f \u0433\u0440\u0430\u043d\u0438\u0446\u0430
}

#: \u0412\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0438\u0435 \u0446\u0435\u043b\u0438 \u043a\u043e\u043c\u0430\u043d\u0434\u044b. \u0412\u044b\u0448\u0435 \u043f\u043e\u0440\u043e\u0433\u043e\u0432, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0441\u0430\u0434\u043a\u0430 \u043d\u0435 \u043b\u043e\u043c\u0430\u043b\u0430 \u043f\u0440\u0438\u0451\u043c\u043a\u0443.
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
    """\u0418\u043d\u0442\u0435\u0440\u0432\u0430\u043b \u0423\u0438\u043b\u044c\u0441\u043e\u043d\u0430. \u041f\u0440\u0438 n = 0 \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 \u0432\u044b\u0440\u043e\u0436\u0434\u0435\u043d\u043d\u044b\u0439 \u0438\u043d\u0442\u0435\u0440\u0432\u0430\u043b [0;1]."""

    if n <= 0:
        return Interval(point=0.0, low=0.0, high=1.0, n=0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return Interval(point=p, low=max(0.0, centre - spread), high=min(1.0, centre + spread), n=n)


def meets_threshold(name: str, interval: Interval) -> bool:
    """\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u043f\u043e\u0440\u043e\u0433\u0430 \u043f\u043e \u043a\u043e\u043d\u0441\u0435\u0440\u0432\u0430\u0442\u0438\u0432\u043d\u043e\u0439 \u0433\u0440\u0430\u043d\u0438\u0446\u0435 \u0438\u043d\u0442\u0435\u0440\u0432\u0430\u043b\u0430."""

    threshold = TZ_THRESHOLDS[name]
    if name == "false_positive_rate":
        return interval.high <= threshold
    return interval.low >= threshold


def f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def key_field_exact_match(gold: str, predicted: str | None) -> bool:
    """Exact Match \u043f\u043e\u043b\u044f \u043f\u0430\u0441\u043f\u043e\u0440\u0442\u0430. None \u0438 \u043f\u0443\u0441\u0442\u0430\u044f \u0441\u0442\u0440\u043e\u043a\u0430 \u2014 \u043f\u0440\u043e\u043c\u0430\u0445, \u043d\u0435 \u00ab\u043f\u043e\u0445\u043e\u0436\u0435\u00bb."""

    if predicted is None or not predicted.strip():
        return False
    return normalize_key_field(gold) == normalize_key_field(predicted)


def key_field_exact_match_interval(
    pairs: list[tuple[str, str | None]],
) -> Interval:
    """\u0414\u043e\u043b\u044f \u0441\u043e\u0432\u043f\u0430\u0432\u0448\u0438\u0445 \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0445 \u043f\u043e\u043b\u0435\u0439. \u041f\u0443\u0441\u0442\u0430\u044f \u0432\u044b\u0431\u043e\u0440\u043a\u0430 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u0435\u0442 \u043f\u043e\u0440\u043e\u0433."""

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
        sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n))
        / 2.0
    )


def _polygon_area(polygon: Polygon) -> float:
    """\u041f\u043b\u043e\u0449\u0430\u0434\u044c \u043f\u043e \u0444\u043e\u0440\u043c\u0443\u043b\u0435 \u0413\u0430\u0443\u0441\u0441\u0430. \u0417\u043d\u0430\u043a \u043e\u0442\u0431\u0440\u0430\u0441\u044b\u0432\u0430\u0435\u0442\u0441\u044f."""

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
    """\u041e\u0434\u043d\u0430 \u0438\u0442\u0435\u0440\u0430\u0446\u0438\u044f Sutherland\u2013Hodgman: \u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043b\u0435\u0432\u0443\u044e \u043f\u043e\u043b\u0443\u043f\u043b\u043e\u0441\u043a\u043e\u0441\u0442\u044c \u0440\u0435\u0431\u0440\u0430."""

    if not polygon:
        return []
    ex = edge_end[0] - edge_start[0]
    ey = edge_end[1] - edge_start[1]

    def _cross(point: Point) -> float:
        # \u0420\u0435\u0431\u0440\u043e \u00d7 (\u0442\u043e\u0447\u043a\u0430 \u2212 \u043d\u0430\u0447\u0430\u043b\u043e): >0 \u0441\u043b\u0435\u0432\u0430 \u043e\u0442 \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043d\u043e\u0433\u043e \u0440\u0435\u0431\u0440\u0430 (\u0432\u043d\u0443\u0442\u0440\u0438 CCW).
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
    """\u041f\u0435\u0440\u0435\u0441\u0435\u0447\u0435\u043d\u0438\u0435. \u041a\u043b\u0438\u043f \u043e\u0440\u0438\u0435\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d CCW; \u0432\u043e\u0433\u043d\u0443\u0442\u044b\u0439 \u043a\u043b\u0438\u043f \u043d\u0435 \u0433\u0430\u0440\u0430\u043d\u0442\u0438\u0440\u043e\u0432\u0430\u043d."""

    output: list[Point] = list(subject)
    clip_ring = _oriented_ccw(clip)
    if len(clip_ring) < 3:
        return ()
    for index, start in enumerate(clip_ring):
        if not output:
            return ()
        output = _clip_by_halfplane(output, start, clip_ring[(index + 1) % len(clip_ring)])
    return tuple(output)


def iou(poly_a: Polygon, poly_b: Polygon) -> float:
    """IoU \u043d\u043e\u0440\u043c\u0430\u043b\u0438\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u043f\u043e\u043b\u0438\u0433\u043e\u043d\u043e\u0432 \u043f\u043e\u0441\u043b\u0435 CropBox/MediaBox/Rotate.

    \u041a\u043e\u043e\u0440\u0434\u0438\u043d\u0430\u0442\u044b \u2014 \u0432 [0;1], Y \u0432\u043d\u0438\u0437, \u043a\u0430\u043a \u0432 `domain/coordinates.py`. \u0412\u044b\u0440\u043e\u0436\u0434\u0435\u043d\u043d\u044b\u0435
    \u043a\u043e\u043d\u0442\u0443\u0440\u044b (\u043f\u043b\u043e\u0449\u0430\u0434\u044c 0) \u0434\u0430\u044e\u0442 0. \u041f\u043e\u0440\u043e\u0433 \u00ab\u043b\u043e\u043a\u0430\u043b\u0438\u0437\u043e\u0432\u0430\u043d\u043e\u00bb \u2014 `IOU_THRESHOLD`, \u043d\u0435 0.95:
    0.95 \u2014 \u043d\u0438\u0436\u043d\u044f\u044f \u0433\u0440\u0430\u043d\u0438\u0446\u0430 Wilson \u043f\u043e \u0434\u043e\u043b\u0435 \u043f\u0430\u0440, \u0430 \u043d\u0435 \u043f\u043e \u043e\u0434\u043d\u043e\u043c\u0443 IoU.
    """

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
    """\u0414\u043e\u043b\u044f \u043f\u0430\u0440 \u0441 IoU \u2265 threshold. \u041f\u0443\u0441\u0442\u0430\u044f \u0432\u044b\u0431\u043e\u0440\u043a\u0430 \u043f\u043e\u0440\u043e\u0433 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u0435\u0442."""

    successes = sum(1 for gold, predicted in pairs if iou(gold, predicted) >= threshold)
    return wilson(successes, len(pairs))


def character_accuracy(reference: str, hypothesis: str) -> float:
    """1 \u2212 CER. Unicode NFC, \u0441\u0445\u043b\u043e\u043f\u044b\u0432\u0430\u043d\u0438\u0435 \u043f\u043e\u0432\u0442\u043e\u0440\u043d\u044b\u0445 \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u0432.

    \u0420\u0435\u0433\u0438\u0441\u0442\u0440 \u043d\u0435 \u0441\u0432\u043e\u0440\u0430\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f: \u0448\u0438\u0444\u0440\u044b \u0438 \u0440\u0435\u0434\u0430\u043a\u0446\u0438\u0438 \u0447\u0443\u0432\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u044c\u043d\u044b \u043a \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0443
    (\u0422\u0417 \u043f. 9.1). \u041d\u0435 \u0441\u043c\u0435\u0448\u0438\u0432\u0430\u0442\u044c \u0441 Exact Match \u043f\u043e\u043b\u0435\u0439.
    """

    def _prepare(s: str) -> str:
        """NFC + \u0441\u0445\u043b\u043e\u043f\u044b\u0432\u0430\u043d\u0438\u0435 \u0434\u0432\u043e\u0439\u043d\u044b\u0445 \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u0432 + \u0437\u0430\u0447\u0438\u0441\u0442\u043a\u0430 \u043a\u0440\u0430\u0451\u0432."""
        return re.sub(r"  +", " ", unicodedata.normalize("NFC", s)).strip()

    ref = _prepare(reference)
    hyp = _prepare(hypothesis)

    # \u0411\u044b\u0441\u0442\u0440\u044b\u0435 \u043f\u0443\u0442\u0438
    if not ref and not hyp:
        return 1.0
    if not ref:
        # \u041f\u0443\u0441\u0442\u043e\u0439 \u044d\u0442\u0430\u043b\u043e\u043d \u043f\u0440\u0438 \u043d\u0435\u043f\u0443\u0441\u0442\u043e\u0439 \u0433\u0438\u043f\u043e\u0442\u0435\u0437\u0435 \u2014 CER \u043d\u0435 \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0451\u043d, \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u043c 0.
        return 0.0
    if ref == hyp:
        return 1.0

    # Wagner\u2013Fischer Levenshtein, O(m\u00b7n) time, O(n) space
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
