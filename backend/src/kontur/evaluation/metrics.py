"""Метрики приёмки (ТЗ п. 14.3).

Считаются по evidence_group, никогда по страницам или файлам. Точечная оценка
публикуется только вместе с размером выборки, coverage и 95% доверительным
интервалом. Порог биномиальных долей берётся по нижней границе интервала;
для FPR — по верхней. Character Accuracy ТЗ — отдельная микро-доля по
символам эталона, не доля строк и не точечный recall.
"""

from __future__ import annotations

import math
import random
import re
import unicodedata
from collections.abc import Mapping, Sequence
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


@dataclass(frozen=True, slots=True)
class PooledCharacterAccuracy:
    """Микро-оценка корпуса OCR.

    CA = 1 − ΣЛевенштейн / Σсимволов эталона. Ноль символов даёт CA и CER
    равными None, не 1.0. WER — по токенам. ``line_exact_match`` — доля
    строк, совпавших целиком; это не Exact Match ключевых полей.
    """

    point: float | None
    cer: float | None
    wer: float | None
    line_exact_match: float | None
    edit_distance: int
    ref_chars: int
    token_distance: int
    ref_tokens: int
    exact_lines: int
    n_lines: int


@dataclass(frozen=True, slots=True)
class LineBootstrap:
    """Перцентильный интервал микро-CA. Единица ресэмпла — строка, не символ.

    `decides_threshold` всегда ложь: при одинаковых строках ширина нулевая,
    и такой интервал не заменяет границу Уилсона.
    """

    point: float
    low: float
    high: float
    n_lines: int

    @property
    def decides_threshold(self) -> bool:
        return False


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


FIELD_KINDS: tuple[str, ...] = (
    "CIPHER",
    "STAGE",
    "REVISION",
    "SHEET_PAGE",
    "ROOM_ELEMENT",
)
FIELD_QUOTA = 30
_CASE_SIGNIFICANT_FIELD: dict[str, bool] = {
    "CIPHER": True,
    "ROOM_ELEMENT": True,
    "STAGE": False,
    "REVISION": False,
    "SHEET_PAGE": False,
}


def _field_text(value: object, *, case_significant: bool) -> str:
    text = prepare_ocr_text(str(value or ""))
    return text if case_significant else text.casefold()


def score_key_fields(fields: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Exact Match по пяти видам полей. Вид с n < 30 в сводку 0,90 не входит.

    Регистр значим у шифра и номера помещения. Стадия, редакция и лист
    сравниваются без регистра. Знаки в шифре не выбрасываются.
    """

    counts: dict[str, list[int]] = {kind: [0, 0] for kind in FIELD_KINDS}
    for item in fields:
        kind = str(item.get("kind") or "").upper()
        if kind not in counts:
            raise ValueError(f"неизвестный вид поля {kind!r}")
        case_significant = _CASE_SIGNIFICANT_FIELD[kind]
        reference = _field_text(item.get("reference"), case_significant=case_significant)
        hypothesis = _field_text(item.get("hypothesis"), case_significant=case_significant)
        counts[kind][1] += 1
        if reference == hypothesis and reference:
            counts[kind][0] += 1
    by_kind: list[dict[str, object]] = []
    summary_matches = 0
    summary_n = 0
    below_quota: list[str] = []
    for kind in FIELD_KINDS:
        matches, n = counts[kind]
        measured = n >= FIELD_QUOTA
        if measured:
            summary_matches += matches
            summary_n += n
        else:
            below_quota.append(kind)
        by_kind.append(
            {
                "kind": kind,
                "matches": matches,
                "n": n,
                "em": None if n == 0 else matches / n,
                "quota": FIELD_QUOTA,
                "measured": measured,
            }
        )
    interval = wilson(summary_matches, summary_n)
    return {
        "by_kind": by_kind,
        "em": None if summary_n == 0 else summary_matches / summary_n,
        "matches": summary_matches,
        "n": summary_n,
        "defined": summary_n > 0,
        "quota": FIELD_QUOTA,
        "kinds_below_quota": below_quota,
        "threshold_met": meets_threshold("key_field_exact_match", interval) if summary_n else False,
        "decides_threshold": summary_n > 0,
    }


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


_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"\S+")


def prepare_ocr_text(value: str) -> str:
    """NFC и любая пробельная последовательность в один пробел.

    Регистр сохраняется. Знаки, точки, дефисы и косая черта не выбрасываются:
    «ИОС4.2-кор3» и «ИОС42кор3» — разные чтения. Латинские двойники кириллицы
    не схлопываются: это другой замер, не CA ТЗ.
    """

    return _WS.sub(" ", unicodedata.normalize("NFC", value)).strip()


def _edit_distance(left: Sequence[object], right: Sequence[object]) -> int:
    """Расстояние правок, O(m·n) время и O(n) память."""

    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def levenshtein(left: str, right: str) -> int:
    """Символьное расстояние Левенштейна."""

    if left == right:
        return 0
    return _edit_distance(left, right)


def character_accuracy(reference: str, hypothesis: str) -> float:
    """Построчный 1 − CER. Unicode NFC, схлопывание повторных пробелов.

    Регистр не сворачивается: шифры и редакции чувствительны к регистру
    (ТЗ п. 9.1). Не смешивать с Exact Match полей и с микро-CA по корпусу:
    среднее построчных CA не равно 1 − ΣЛевенштейн / Σсимволов.
    """

    ref = prepare_ocr_text(reference)
    hyp = prepare_ocr_text(hypothesis)
    if not ref and not hyp:
        return 1.0
    if not ref:
        return 0.0
    if ref == hyp:
        return 1.0
    return max(0.0, 1.0 - levenshtein(ref, hyp) / len(ref))


def _line_cost(reference: str, hypothesis: str) -> tuple[int, int]:
    """Расстояние и число символов эталона. Пустой эталон в знаменатель не входит."""

    ref = prepare_ocr_text(reference)
    if not ref:
        return (0, 0)
    return (levenshtein(ref, prepare_ocr_text(hypothesis)), len(ref))


def pooled_character_accuracy(
    pairs: Sequence[tuple[str, str]],
) -> PooledCharacterAccuracy:
    """Микро-CA, CER, WER и доля точных строк.

    Пустой эталон в сумму символов не входит. Ноль строк даёт EM = None,
    не 1.0. Ноль токенов даёт WER = None.
    """

    distance = 0
    chars = 0
    token_distance = 0
    ref_tokens = 0
    exact_lines = 0
    for reference, hypothesis in pairs:
        ref = prepare_ocr_text(reference)
        hyp = prepare_ocr_text(hypothesis)
        if ref == hyp:
            exact_lines += 1
        if ref:
            distance += levenshtein(ref, hyp)
            chars += len(ref)
        ref_token_list = _TOKEN.findall(ref)
        token_distance += _edit_distance(ref_token_list, _TOKEN.findall(hyp))
        ref_tokens += len(ref_token_list)
    point = None if chars <= 0 else max(0.0, 1.0 - distance / chars)
    return PooledCharacterAccuracy(
        point=point,
        cer=None if point is None else 1.0 - point,
        wer=None if ref_tokens <= 0 else token_distance / ref_tokens,
        line_exact_match=None if not pairs else exact_lines / len(pairs),
        edit_distance=distance,
        ref_chars=chars,
        token_distance=token_distance,
        ref_tokens=ref_tokens,
        exact_lines=exact_lines,
        n_lines=len(pairs),
    )


def pooled_ca_line_bootstrap(
    pairs: Sequence[tuple[str, str]],
    *,
    rounds: int = 1000,
    seed: int = 7,
) -> LineBootstrap | None:
    """95% перцентильный интервал микро-CA при ресэмпле строк.

    Символ испытанием Бернулли не считается: соседние символы строки зависимы.
    Нет символов эталона — интервала нет, не [0; 1] и не 1.0.
    """

    costs = [_line_cost(reference, hypothesis) for reference, hypothesis in pairs]
    if sum(chars for _distance, chars in costs) <= 0 or rounds <= 0:
        return None
    observed = pooled_character_accuracy(pairs)
    if observed.point is None:
        return None
    rng = random.Random(seed)  # noqa: S311 — ресэмпл, не криптография
    n_lines = len(costs)
    stats: list[float] = []
    for _ in range(rounds):
        distance = 0
        chars = 0
        for _draw in range(n_lines):
            line_distance, line_chars = costs[rng.randrange(n_lines)]
            distance += line_distance
            chars += line_chars
        if chars <= 0:
            continue
        stats.append(max(0.0, 1.0 - distance / chars))
    if not stats:
        return None
    stats.sort()
    last = len(stats) - 1
    return LineBootstrap(
        point=observed.point,
        low=stats[int(0.025 * last)],
        high=stats[int(0.975 * last)],
        n_lines=n_lines,
    )
