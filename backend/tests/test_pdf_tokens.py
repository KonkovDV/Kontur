"""Gate C: PDF → токены. Identity — SHA-256 содержимого, не имя файла."""

from __future__ import annotations

import ctypes
import io
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest

from kontur.application.passport import read_passport
from kontur.domain.geometry import polygon_in_unit_square
from kontur.infrastructure.pdfium_tokens import (
    ENGINE_NAME,
    extract_pdf_bytes,
    extract_pdf_path,
    file_sha256,
    flatten_tokens,
)


def _wchar(text: str) -> ctypes.Array[ctypes.c_ushort]:
    raw = (text + "\x00").encode("utf-16-le")
    return (ctypes.c_ushort * (len(raw) // 2)).from_buffer_copy(raw)


def ascii_pdf(
    text: str,
    *,
    x: float = 12.0,
    y: float = 20.0,
    width: float = 200.0,
    height: float = 200.0,
    crop: tuple[float, float, float, float] | None = None,
    rotate: int = 0,
) -> bytes:
    """Минимальный векторный PDF латиницей: кириллица требует встраивания шрифта."""

    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(width, height)
    obj = pdfium_c.FPDFPageObj_NewTextObj(pdf, b"Helvetica", 10)
    pdfium_c.FPDFText_SetText(obj, _wchar(text))
    pdfium_c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
    pdfium_c.FPDFPage_InsertObject(page, obj)
    if crop is not None:
        page.set_cropbox(*crop)
    if rotate:
        page.set_rotation(rotate)
    pdfium_c.FPDFPage_GenerateContent(page)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()


def empty_pdf() -> bytes:
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(100, 100)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()


def test_engine_is_vector_pdfium() -> None:
    assert ENGINE_NAME == "pdfium-vector"


def test_same_bytes_keep_identity_under_rename() -> None:
    data = ascii_pdf("CODE 12345-PZ Rev 2 Sheet 1")
    first = extract_pdf_bytes(data)
    second = extract_pdf_bytes(data)
    assert first.file_hash == second.file_hash == file_sha256(data)
    assert first.file_hash != file_sha256(data + b"\x00")


def test_extract_path_matches_bytes_hash(tmp_path: Path) -> None:
    data = ascii_pdf("CODE 12345-PZ")
    renamed = tmp_path / "moved" / "other-name.pdf"
    renamed.parent.mkdir()
    renamed.write_bytes(data)
    from_path = extract_pdf_path(renamed)
    assert from_path.file_hash == file_sha256(data)
    assert from_path.pages[0].has_embedded_text is True
    assert from_path.layer_kind == "vector"


def test_empty_page_is_raster_without_ocr() -> None:
    extracted = extract_pdf_bytes(empty_pdf())
    assert extracted.layer_kind == "raster"
    assert flatten_tokens(extracted) == ()
    assert extracted.pages[0].has_embedded_text is False


def test_corrupt_pdf_is_an_error_not_empty_success() -> None:
    with pytest.raises(ValueError, match="не PDF"):
        extract_pdf_bytes(b"not-a-pdf")
    with pytest.raises(ValueError, match="пустой"):
        extract_pdf_bytes(b"")


def test_tokens_stay_in_unit_square() -> None:
    extracted = extract_pdf_bytes(ascii_pdf("CODE 12345-PZ Rev 2 Sheet 1"))
    tokens = flatten_tokens(extracted)
    assert tokens
    for token in tokens:
        assert polygon_in_unit_square(token.polygon_norm)
        assert token.page == 1


def _dark_pixels(png: bytes, polygon: object) -> tuple[int, int, int]:
    """Сколько тёмных пикселей внутри bbox polygon_norm и размер PNG."""

    from PIL import Image

    image = Image.open(io.BytesIO(png)).convert("L")
    width, height = image.size
    assert isinstance(polygon, tuple)
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    x0 = max(0, int(min(xs) * width))
    x1 = min(width, int(max(xs) * width) + 1)
    y0 = max(0, int(min(ys) * height))
    y1 = min(height, int(max(ys) * height) + 1)
    assert x1 > x0 and y1 > y0
    crop = image.crop((x0, y0, x1, y1))
    loaded = crop.load()
    assert loaded is not None
    dark = sum(
        1
        for y in range(crop.height)
        for x in range(crop.width)
        if loaded[x, y] < 200
    )
    return dark, width, height


def test_rotated_page_polygon_lands_on_png_ink() -> None:
    """Поворот листа: polygon_norm в [0;1] и на краске того PNG, что отдаёт экран."""

    from kontur.infrastructure.pdfium_page import render_page_png

    wide = dict(width=360.0, height=120.0, x=16.0, y=28.0)
    cases = (
        (ascii_pdf("CODE 12345-PZ", **wide), 0, True),
        (ascii_pdf("CODE 12345-PZ", rotate=90, **wide), 90, False),
        (ascii_pdf("CODE 12345-PZ", rotate=180, **wide), 180, True),
        (ascii_pdf("CODE 12345-PZ", rotate=270, **wide), 270, False),
    )
    for data, rotate, expect_wide in cases:
        extracted = extract_pdf_bytes(data)
        assert extracted.pages[0].frame.rotate == rotate
        tokens = flatten_tokens(extracted)
        assert tokens
        for token in tokens:
            assert polygon_in_unit_square(token.polygon_norm)
        png = render_page_png(data, 1)
        assert png.startswith(b"\x89PNG")
        dark, width, height = _dark_pixels(png, tokens[0].polygon_norm)
        assert dark >= 8
        assert (width > height) is expect_wide


def test_text_outside_cropbox_is_not_a_token() -> None:
    data = ascii_pdf("SECRET", x=12, y=20, crop=(80, 80, 180, 180))
    extracted = extract_pdf_bytes(data)
    assert flatten_tokens(extracted) == ()
    assert extracted.pages[0].layer_kind == "raster"


def test_ascii_stamp_feeds_passport_without_filename_code() -> None:
    data = ascii_pdf("CODE 12345-PZ Rev 2 Sheet 1 Stage PD")
    extracted = extract_pdf_bytes(data)
    passport = read_passport(
        flatten_tokens(extracted),
        file_id="file-pd",
        file_hash=extracted.file_hash,
        filename="RD_moved.pdf",
        pages=len(extracted.pages),
        layer_kind=extracted.layer_kind,
        rotate=extracted.pages[0].frame.rotate,
        media_box=extracted.pages[0].frame.media,
        crop_box=extracted.pages[0].frame.crop,
    )
    assert passport.document_code == "12345-PZ"
    assert passport.revision == "2"
    assert passport.sheet == "1"
    assert passport.doc_stage is None
    assert passport.needs_clarification is True
    assert passport.file_hash == file_sha256(data)
