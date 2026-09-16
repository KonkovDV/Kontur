"""Gate D: геометрия страницы. Пока каркас — тесты помечены как ожидаемо падающие.

Как только CoordinateMapper реализован, `strict=True` заставит снять xfail:
скрытая регрессия здесь означает, что доказательство указывает не на то место,
что читал экстрактор, — дефект класса S0.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.xfail(reason="L3 CoordinateMapper не реализован", strict=True)

ROTATIONS = (0, 90, 180, 270)


def test_rotation_roundtrip_preserves_polygon() -> None:
    raise NotImplementedError("для каждого угла из ROTATIONS: to_norm -> to_source = исходный")


def test_cropbox_offset_is_respected() -> None:
    raise NotImplementedError("CropBox != MediaBox: нормализация по видимой области")


def test_negative_origin_page() -> None:
    raise NotImplementedError("страница с отрицательным origin")


def test_mixed_page_sizes_in_one_document() -> None:
    raise NotImplementedError("A4 + A1 + landscape в одном файле")


def test_normalized_polygon_stays_in_unit_square() -> None:
    raise NotImplementedError("все координаты в [0;1]")


def test_bbox_is_derived_from_polygon() -> None:
    raise NotImplementedError("хранится polygon; bbox вычисляется, а не наоборот")
