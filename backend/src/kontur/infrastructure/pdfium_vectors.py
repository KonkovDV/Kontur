"""Векторные штрихи страницы: занятость сетки, не распознавание условных знаков.

Читает PATH-объекты PDFium на одном листе. Текст и OCR не подменяются.
Штамп нижней полосы в сетку не входит: там основная надпись, не чертёж.
"""

from __future__ import annotations

from dataclasses import dataclass

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

from kontur.domain.coordinates import PageFrame, to_normalized
from kontur.domain.models import Polygon

GRID = 16
STAMP_Y = 0.85


@dataclass(frozen=True, slots=True)
class DrawingPage:
    page: int
    path_count: int
    occupied: frozenset[tuple[int, int]]
    grid: int = GRID


@dataclass(frozen=True, slots=True)
class DrawingComparison:
    left_paths: int
    right_paths: int
    jaccard: float | None
    comparable: bool


def _box(values: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    left, bottom, right, top = values
    return (float(left), float(bottom), float(right), float(top))


def _quad(left: float, bottom: float, right: float, top: float) -> Polygon:
    return ((left, bottom), (right, bottom), (right, top), (left, top))


def _cell(norm_x: float, norm_y: float, grid: int) -> tuple[int, int] | None:
    if norm_y >= STAMP_Y:
        return None
    if not (0.0 <= norm_x <= 1.0 and 0.0 <= norm_y <= 1.0):
        return None
    col = min(grid - 1, int(norm_x * grid))
    row = min(grid - 1, int(norm_y * grid))
    return col, row


def drawing_occupancy(data: bytes, page_number: int, *, grid: int = GRID) -> DrawingPage:
    """Сетка штрихов одного листа. Пустой или битый PDF — ошибка, не пустой успех."""

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
        media = _box(tuple(page.get_mediabox()))
        crop_raw = page.get_cropbox()
        crop = _box(tuple(crop_raw)) if crop_raw is not None else media
        frame = PageFrame(media=media, crop=crop, rotate=int(page.get_rotation()))
        occupied: set[tuple[int, int]] = set()
        path_count = 0
        for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=0):
            try:
                left, bottom, right, top = (float(v) for v in obj.get_bounds())
            finally:
                obj.close()
            if right <= left or top <= bottom:
                continue
            path_count += 1
            try:
                polygon = to_normalized(_quad(left, bottom, right, top), frame)
            except ValueError:
                continue
            xs = [point[0] for point in polygon]
            ys = [point[1] for point in polygon]
            cell = _cell((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, grid)
            if cell is not None:
                occupied.add(cell)
        return DrawingPage(
            page=page_number,
            path_count=path_count,
            occupied=frozenset(occupied),
            grid=grid,
        )
    finally:
        document.close()


def compare_drawings(
    left: DrawingPage,
    right: DrawingPage,
    *,
    min_paths: int = 40,
) -> DrawingComparison:
    """Доля общей занятости. Мало штрихов — листы не сравниваются как чертёж."""

    comparable = left.path_count >= min_paths and right.path_count >= min_paths
    if not comparable:
        return DrawingComparison(left.path_count, right.path_count, None, False)
    union = left.occupied | right.occupied
    if not union:
        return DrawingComparison(left.path_count, right.path_count, None, False)
    shared = len(left.occupied & right.occupied) / len(union)
    return DrawingComparison(left.path_count, right.path_count, shared, True)
