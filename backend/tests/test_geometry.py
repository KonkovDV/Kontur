"""bbox считается из polygon и обратно не подменяет контур."""

from __future__ import annotations

import pytest

from kontur.domain.geometry import bbox_from_polygon, polygon_in_unit_square, union_rect_polygon


def test_bbox_is_derived_from_polygon() -> None:
    polygon = ((0.1, 0.2), (0.4, 0.2), (0.4, 0.5), (0.1, 0.5))
    assert bbox_from_polygon(polygon) == (0.1, 0.2, 0.4, 0.5)


def test_union_rect_covers_all_fragments() -> None:
    left = ((0.0, 0.0), (0.2, 0.0), (0.2, 0.1), (0.0, 0.1))
    right = ((0.5, 0.4), (0.7, 0.4), (0.7, 0.6), (0.5, 0.6))
    union = union_rect_polygon((left, right))
    assert bbox_from_polygon(union) == (0.0, 0.0, 0.7, 0.6)


def test_normalized_polygon_rejects_out_of_page() -> None:
    assert polygon_in_unit_square(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)))
    assert not polygon_in_unit_square(((0.0, 0.0), (1.2, 0.0), (1.2, 1.0), (0.0, 1.0)))


def test_polygon_shorter_than_three_points_is_invalid() -> None:
    with pytest.raises(ValueError, match="трёх"):
        bbox_from_polygon(((0.0, 0.0), (1.0, 1.0)))
