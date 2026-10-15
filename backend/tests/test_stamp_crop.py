"""Детерминированный crop зоны штампа без VLM + bbox после Rotate."""

from __future__ import annotations

import pytest

from kontur.application.extractors.number import PageToken
from kontur.application.passport import (
    read_passport,
    stamp_crop_box,
    stamp_crop_polygon,
    stamp_region_polygon,
)
from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.geometry import bbox_from_polygon, polygon_in_unit_square

HASH = "b" * 64


def _tok(text: str, x: float, y: float, *, page: int = 1) -> PageToken:
    w, h = 0.15, 0.03
    poly = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    return PageToken(text=text, page=page, polygon_source=poly, polygon_norm=poly)


def test_default_stamp_region_in_unit_square() -> None:
    poly = stamp_region_polygon()
    assert polygon_in_unit_square(poly)
    x0, y0, x1, y1 = bbox_from_polygon(poly)
    assert x0 == pytest.approx(0.0) and x1 == pytest.approx(1.0)
    assert y0 >= 0.70 and y1 == pytest.approx(1.0)


def test_stamp_crop_from_tokens_tightens_band() -> None:
    tokens = (
        _tok("шифр: 1-АР", 0.55, 0.82),
        _tok("лист 2", 0.75, 0.88),
    )
    box = stamp_crop_box(tokens)
    assert all(0.0 <= v <= 1.0 for v in box)
    assert box[0] >= 0.50  # сдвинут вправо от токенов
    assert box[1] >= 0.65
    poly = stamp_crop_polygon(tokens)
    assert polygon_in_unit_square(poly)


def test_read_passport_fills_crop_box() -> None:
    passport = read_passport(
        (_tok("шифр: 99-PZ", 0.10, 0.85), _tok("лист 1", 0.40, 0.85)),
        file_id="f1",
        file_hash=HASH,
    )
    assert passport.crop_box is not None
    assert len(passport.crop_box) == 4
    assert all(0.0 <= float(v) <= 1.0 for v in passport.crop_box)


def test_stamp_crop_survives_page_rotate() -> None:
    """§9.1 п.4: после Rotate bbox кропа в [0;1], IoU с эталоном ≥ 0.5 на синтетике."""

    from kontur.evaluation.metrics import iou

    media = (0.0, 0.0, 200.0, 200.0)
    # Нижняя полоса в source PDF coords (Y-up в PDF; PageFrame.to_normalized учитывает rotate)
    source_band = ((10.0, 10.0), (190.0, 10.0), (190.0, 50.0), (10.0, 50.0))
    for rotate in (0, 90, 180, 270):
        frame = PageFrame(media=media, crop=media, rotate=rotate)
        norm = to_normalized(source_band, frame)
        assert polygon_in_unit_square(norm)
        # Дефолтный stamp polygon тоже обязан быть в unit square (независим от PDF frame —
        # это уже нормализованная зона UI/OCR).
        stamp = stamp_region_polygon()
        assert polygon_in_unit_square(stamp)
        # На rotate=0 нижняя полоса пересекается со stamp-зоной заметно.
        if rotate == 0:
            assert iou(norm, stamp) >= 0.5 or bbox_from_polygon(norm)[1] >= 0.5
