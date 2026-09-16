"""Геометрия доказательства: хранится polygon, bbox — производное (инвариант 7)."""

from __future__ import annotations

from kontur.domain.models import Polygon

BBox = tuple[float, float, float, float]


def bbox_from_polygon(polygon: Polygon) -> BBox:
    """Осепараллельный bbox. Не хранится отдельно и не является источником истины."""

    if len(polygon) < 3:
        raise ValueError("polygon должен содержать не меньше трёх точек")
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def union_rect_polygon(polygons: tuple[Polygon, ...]) -> Polygon:
    """Охватывающий прямоугольник как четырёхугольник. Исходные контуры не теряются
    у вызывающего: это производная зона значения, не замена фрагментов."""

    if not polygons:
        raise ValueError("нет контуров для объединения")
    x0, y0, x1, y1 = bbox_from_polygon(polygons[0])
    for polygon in polygons[1:]:
        left, top, right, bottom = bbox_from_polygon(polygon)
        x0 = min(x0, left)
        y0 = min(y0, top)
        x1 = max(x1, right)
        y1 = max(y1, bottom)
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def polygon_in_unit_square(polygon: Polygon) -> bool:
    """Нормализованный контур обязан лежать в [0;1] после CropBox/MediaBox/Rotate."""

    return all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in polygon)


def y_overlap(left: Polygon, right: Polygon) -> bool:
    """Пересечение по вертикали: ячейка таблицы обычно на одной строке с подписью."""

    _, top_a, _, bottom_a = bbox_from_polygon(left)
    _, top_b, _, bottom_b = bbox_from_polygon(right)
    return top_a < bottom_b and top_b < bottom_a


def reading_key(page: int, polygon: Polygon) -> tuple[int, float, float]:
    """Порядок чтения: страница, строка сверху вниз, затем слева направо.

    Для синтетических страниц ось Y направлена вниз (меньше — выше).
    """

    x0, y0, _, _ = bbox_from_polygon(polygon)
    return (page, round(y0, 4), round(x0, 4))
