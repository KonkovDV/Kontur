"""Система координат страницы PDF: MediaBox, CropBox, Rotate.

Нормализованное пространство — [0;1], ось Y вниз (порядок чтения сверху вниз).
Исходное пространство — user space PDF, Y вверх. Единственное место, где
это преобразование считается: компаратор и экстрактор координат не знают.
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.domain.geometry import bbox_from_polygon, polygon_in_unit_square
from kontur.domain.models import Point, Polygon

BBox = tuple[float, float, float, float]
ALLOWED_ROTATIONS = frozenset({0, 90, 180, 270})


@dataclass(frozen=True, slots=True)
class PageFrame:
    """Геометрия одной страницы. crop — видимая область (CropBox или MediaBox)."""

    media: BBox
    crop: BBox
    rotate: int = 0

    def __post_init__(self) -> None:
        if self.rotate not in ALLOWED_ROTATIONS:
            raise ValueError(f"Rotate {self.rotate} не из {{0, 90, 180, 270}}")
        for name, box in (("media", self.media), ("crop", self.crop)):
            left, bottom, right, top = box
            if right <= left or top <= bottom:
                raise ValueError(f"{name} вырожден: {box}")


def _to_view(x: float, y: float, frame: PageFrame) -> tuple[float, float, float, float]:
    left, bottom, right, top = frame.crop
    width, height = right - left, top - bottom
    u, v = x - left, y - bottom
    rotate = frame.rotate
    if rotate == 0:
        return u, v, width, height
    if rotate == 90:
        return v, width - u, height, width
    if rotate == 180:
        return width - u, height - v, width, height
    return height - v, u, height, width


def _from_view(vx: float, vy: float, frame: PageFrame) -> Point:
    left, bottom, right, top = frame.crop
    width, height = right - left, top - bottom
    rotate = frame.rotate
    if rotate == 0:
        u, v = vx, vy
    elif rotate == 90:
        u, v = width - vy, vx
    elif rotate == 180:
        u, v = width - vx, height - vy
    else:
        u, v = vy, height - vx
    return (left + u, bottom + v)


def to_normalized(polygon: Polygon, frame: PageFrame) -> Polygon:
    """User space → [0;1], Y вниз, относительно CropBox после Rotate."""

    points: list[Point] = []
    for x, y in polygon:
        vx, vy, view_w, view_h = _to_view(x, y, frame)
        nx = vx / view_w
        ny = 1.0 - (vy / view_h)
        points.append((nx, ny))
    result = tuple(points)
    if not polygon_in_unit_square(result):
        # допускаем касание границы; выход за страницу — ошибка источника
        x0, y0, x1, y1 = bbox_from_polygon(result)
        if x0 < -1e-9 or y0 < -1e-9 or x1 > 1 + 1e-9 or y1 > 1 + 1e-9:
            raise ValueError("нормализованный polygon выходит за [0;1]")
        result = tuple(
            (min(1.0, max(0.0, px)), min(1.0, max(0.0, py))) for px, py in result
        )
    return result


def polygons_from_view_pixels(
    left: float,
    top: float,
    right: float,
    bottom: float,
    image_size: tuple[int, int],
    frame: PageFrame,
) -> tuple[Polygon, Polygon] | None:
    """Пиксели кадра pdfium → polygon источника и [0;1].

    ``page.render`` уже применяет ``/Rotate``: ось X вправо, Y вниз,
    размер кадра — видимая страница. Доля пикселя и есть polygon_norm.
    """

    img_w, img_h = image_size
    if img_w <= 0 or img_h <= 0 or right <= left or bottom <= top:
        return None
    polygon_norm = (
        (left / img_w, top / img_h),
        (right / img_w, top / img_h),
        (right / img_w, bottom / img_h),
        (left / img_w, bottom / img_h),
    )
    if not polygon_in_unit_square(polygon_norm):
        return None
    return to_source(polygon_norm, frame), polygon_norm


def to_source(polygon_norm: Polygon, frame: PageFrame) -> Polygon:
    """[0;1], Y вниз → user space PDF."""

    left, bottom, right, top = frame.crop
    width, height = right - left, top - bottom
    view_w, view_h = (height, width) if frame.rotate % 180 == 90 else (width, height)
    points: list[Point] = []
    for nx, ny in polygon_norm:
        vx = nx * view_w
        vy = (1.0 - ny) * view_h
        points.append(_from_view(vx, vy, frame))
    return tuple(points)
