"""Сечение воздуховода по паре параллельных штрихов.

Ширина на бумаге (пункты) переводится в миллиметры и умножается на
знаменатель масштаба: реальный размер = длина_пт × 25.4/72 × N.
Прямоугольник 400×200 пт при 1:100 — это не 400×200 мм.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

from kontur.domain.models import Polygon

PT_TO_MM = 25.4 / 72.0
_THIN_PT = 3.0


@dataclass(frozen=True, slots=True)
class Segment:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)


DEFAULT_ANGLE_DEG = 2.0
DEFAULT_MIN_OVERLAP = 0.6
DEFAULT_MIN_LENGTH_PT = 20.0
DEFAULT_GAP_MIN_PT = 2.0
DEFAULT_GAP_MAX_PT = 60.0
DEFAULT_READ_TOLERANCE_REL = 0.02


@dataclass(frozen=True, slots=True)
class DuctPair:
    gap_pt: float
    reverse_gap_pt: float
    span_pt: float
    width_mm: float
    polygon: Polygon


def width_mm(gap_pt: float, scale_denominator: int) -> float:
    """Реальная ширина, мм. Масштаб 1:N, N — знаменатель."""

    if scale_denominator < 1:
        raise ValueError("знаменатель масштаба должен быть ≥ 1")
    if gap_pt <= 0:
        raise ValueError("зазор штрихов должен быть > 0")
    return gap_pt * PT_TO_MM * scale_denominator


def gaps_agree(primary: float, reverse: float, *, tolerance_rel: float) -> bool:
    """Два замера зазора. Расхождение больше допуска — не усредняем."""

    if primary <= 0 or tolerance_rel < 0:
        return False
    return abs(primary - reverse) / primary <= tolerance_rel


def choose_pair(pairs: list[DuctPair]) -> DuctPair | None:
    """Самый длинный прогон. При равенстве — более узкий зазор. Пороги не подбираются по золоту."""

    if not pairs:
        return None
    return max(pairs, key=lambda item: (item.span_pt, -item.gap_pt))


def pair_parallel(
    segments: list[Segment],
    scale_denominator: int,
    *,
    angle_deg: float = 2.0,
    min_overlap: float = 0.6,
    min_length_pt: float = 20.0,
    gap_min_pt: float = 2.0,
    gap_max_pt: float = 60.0,
) -> list[DuctPair]:
    """Пары почти параллельных отрезков с перекрытием проекций."""

    usable = [item for item in segments if item.length >= min_length_pt]
    found: list[DuctPair] = []
    for index, left in enumerate(usable):
        for right in usable[index + 1 :]:
            measured = _gap_if_parallel(
                left,
                right,
                angle_deg=angle_deg,
                min_overlap=min_overlap,
                gap_min_pt=gap_min_pt,
                gap_max_pt=gap_max_pt,
            )
            if measured is None:
                continue
            gap, reverse, span = measured
            found.append(
                DuctPair(
                    gap_pt=gap,
                    reverse_gap_pt=reverse,
                    span_pt=span,
                    width_mm=width_mm(gap, scale_denominator),
                    polygon=_quad(left, right),
                )
            )
    return found


def segments_on_page(data: bytes, page_number: int) -> list[Segment]:
    """Отрезки из тонких PATH. Прямоугольник и форма XObject не пара линий."""

    if page_number < 1:
        raise ValueError("номер страницы начинается с 1")
    if not data:
        raise ValueError("PDF не разбирается: пустой файл")
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise ValueError("PDF не разбирается: повреждён или это не PDF") from exc
    try:
        if page_number > len(document):
            raise ValueError(f"в PDF нет страницы {page_number}")
        page = document[page_number - 1]
        segments: list[Segment] = []
        for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=0):
            try:
                left, bottom, right, top = (float(value) for value in obj.get_bounds())
            finally:
                obj.close()
            width = right - left
            height = top - bottom
            if width <= 0 or height <= 0:
                continue
            if width < _THIN_PT and height >= 20:
                mid_x = (left + right) / 2
                segments.append(Segment(mid_x, bottom, mid_x, top))
            elif height < _THIN_PT and width >= 20:
                mid_y = (bottom + top) / 2
                segments.append(Segment(left, mid_y, right, mid_y))
        return segments
    finally:
        document.close()


def _direction(segment: Segment) -> tuple[float, float]:
    length = segment.length
    return (segment.x1 - segment.x0) / length, (segment.y1 - segment.y0) / length


def _gap_if_parallel(
    left: Segment,
    right: Segment,
    *,
    angle_deg: float,
    min_overlap: float,
    gap_min_pt: float,
    gap_max_pt: float,
) -> tuple[float, float, float] | None:
    dir_x, dir_y = _direction(left)
    other_x, other_y = _direction(right)
    dot = abs(dir_x * other_x + dir_y * other_y)
    dot = min(1.0, dot)
    if math.degrees(math.acos(dot)) > angle_deg:
        return None
    mid_x = (right.x0 + right.x1) / 2
    mid_y = (right.y0 + right.y1) / 2
    gap = _line_distance(mid_x, mid_y, left)
    if gap < gap_min_pt or gap > gap_max_pt:
        return None
    if _overlap_ratio(left, right, dir_x, dir_y) < min_overlap:
        return None
    reverse = _line_distance((left.x0 + left.x1) / 2, (left.y0 + left.y1) / 2, right)
    return gap, reverse, min(left.length, right.length)


def _line_distance(px: float, py: float, segment: Segment) -> float:
    dir_x, dir_y = _direction(segment)
    return abs((px - segment.x0) * dir_y - (py - segment.y0) * dir_x)


def _project(segment: Segment, dir_x: float, dir_y: float) -> tuple[float, float]:
    start = segment.x0 * dir_x + segment.y0 * dir_y
    end = segment.x1 * dir_x + segment.y1 * dir_y
    return (min(start, end), max(start, end))


def _overlap_ratio(left: Segment, right: Segment, dir_x: float, dir_y: float) -> float:
    a0, a1 = _project(left, dir_x, dir_y)
    b0, b1 = _project(right, dir_x, dir_y)
    overlap = min(a1, b1) - max(a0, b0)
    shorter = min(a1 - a0, b1 - b0)
    if shorter <= 0 or overlap <= 0:
        return 0.0
    return overlap / shorter


def _quad(left: Segment, right: Segment) -> Polygon:
    return (
        (left.x0, left.y0),
        (left.x1, left.y1),
        (right.x1, right.y1),
        (right.x0, right.y0),
    )
