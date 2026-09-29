"""Gate D-prep: MediaBox, CropBox, Rotate. Нормализация — единственное место Y-down."""

from __future__ import annotations

import pytest

from kontur.domain.coordinates import PageFrame, to_normalized, to_source
from kontur.domain.geometry import bbox_from_polygon, polygon_in_unit_square

ROTATIONS = (0, 90, 180, 270)
SQUARE = ((10.0, 20.0), (40.0, 20.0), (40.0, 50.0), (10.0, 50.0))


def _frame(
    *,
    media: tuple[float, float, float, float] = (0.0, 0.0, 200.0, 200.0),
    crop: tuple[float, float, float, float] | None = None,
    rotate: int = 0,
) -> PageFrame:
    return PageFrame(media=media, crop=crop or media, rotate=rotate)


def _almost(left: object, right: object) -> None:
    assert isinstance(left, tuple) and isinstance(right, tuple)
    assert len(left) == len(right)
    for a, b in zip(left, right, strict=True):
        if isinstance(a, tuple) and isinstance(b, tuple):
            _almost(a, b)
        else:
            assert a == pytest.approx(b, abs=1e-9)


def test_rotation_roundtrip_preserves_polygon() -> None:
    for rotate in ROTATIONS:
        frame = _frame(rotate=rotate)
        restored = to_source(to_normalized(SQUARE, frame), frame)
        _almost(restored, SQUARE)


def test_cropbox_offset_is_respected() -> None:
    frame = _frame(crop=(50.0, 50.0, 150.0, 150.0))
    # нижний левый угол видимой области → (0, 1) при Y вниз
    corner = ((50.0, 50.0), (60.0, 50.0), (60.0, 60.0), (50.0, 60.0))
    norm = to_normalized(corner, frame)
    assert norm[0][0] == pytest.approx(0.0)
    assert norm[0][1] == pytest.approx(1.0)


def test_negative_origin_page() -> None:
    frame = _frame(media=(-10.0, -20.0, 590.0, 822.0), crop=(-10.0, -20.0, 590.0, 822.0))
    origin = ((-10.0, -20.0), (0.0, -20.0), (0.0, 0.0), (-10.0, 0.0))
    norm = to_normalized(origin, frame)
    assert norm[0] == pytest.approx((0.0, 1.0))
    _almost(to_source(norm, frame), origin)


def test_mixed_page_sizes_in_one_document() -> None:
    a4 = _frame(media=(0.0, 0.0, 595.0, 842.0))
    a1 = _frame(media=(0.0, 0.0, 1684.0, 2384.0))
    landscape = _frame(media=(0.0, 0.0, 842.0, 595.0))
    for frame, point in (
        (a4, (297.5, 421.0)),
        (a1, (842.0, 1192.0)),
        (landscape, (421.0, 297.5)),
    ):
        x, y = point
        poly = ((x, y), (x + 10, y), (x + 10, y + 10), (x, y + 10))
        norm = to_normalized(poly, frame)
        assert polygon_in_unit_square(norm)


def test_normalized_polygon_stays_in_unit_square() -> None:
    for rotate in ROTATIONS:
        frame = _frame(rotate=rotate)
        norm = to_normalized(SQUARE, frame)
        assert polygon_in_unit_square(norm)


def test_bbox_is_derived_from_polygon() -> None:
    frame = _frame()
    norm = to_normalized(SQUARE, frame)
    x0, y0, x1, y1 = bbox_from_polygon(norm)
    xs = [p[0] for p in norm]
    ys = [p[1] for p in norm]
    assert (x0, y0, x1, y1) == (min(xs), min(ys), max(xs), max(ys))


def test_point_outside_crop_is_rejected() -> None:
    frame = _frame(crop=(0.0, 0.0, 100.0, 100.0))
    outside = ((150.0, 10.0), (160.0, 10.0), (160.0, 20.0), (150.0, 20.0))
    with pytest.raises(ValueError, match="\\[0;1\\]"):
        to_normalized(outside, frame)


def test_illegal_rotation_is_rejected() -> None:
    with pytest.raises(ValueError, match="Rotate"):
        _frame(rotate=45)
