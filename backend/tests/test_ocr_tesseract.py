"""Контракт OCR-адаптера: fail-closed, без AVAILABLE и без закрытия гейта I.

CA и Wilson живут в evaluation.metrics (z=1.96). Дублировать их здесь
и считать wilson(290, 300) проходом пилота нельзя.
"""

from __future__ import annotations

import pytest
from test_pdf_tokens import empty_pdf

from kontur.application.extractors.number import PageToken, engine_of, extract_number
from kontur.application.process_pipeline import (
    PipelineFile,
    _maybe_ocr,
    run_process_pipeline,
)
from kontur.application.scenarios import CompletenessMap
from kontur.domain.capabilities import capabilities_payload
from kontur.domain.coordinates import PageFrame
from kontur.domain.geometry import polygon_in_unit_square
from kontur.domain.models import DocStage, ExtractionEngine
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.evaluation import metrics
from kontur.infrastructure import ocr_tesseract
from kontur.infrastructure.ocr_tesseract import (
    expand_user_region,
    fill_empty_raster_pages,
    raster_pages_need_ocr,
    tokens_from_tesseract_payload,
)
from kontur.infrastructure.pdf_guard import PdfParseTimeoutError
from kontur.infrastructure.pdfium_tokens import (
    PdfDocumentTokens,
    PdfPageTokens,
    extract_pdf_bytes,
    file_sha256,
)

HASH = "a" * 64


def _completeness_pd() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _raster_page(*, rotate: int = 0, tokens: tuple[PageToken, ...] = ()) -> PdfPageTokens:
    frame = PageFrame(
        media=(0.0, 0.0, 100.0, 100.0),
        crop=(0.0, 0.0, 100.0, 100.0),
        rotate=rotate,
    )
    return PdfPageTokens(
        page=1,
        frame=frame,
        tokens=tokens,
        has_embedded_text=bool(tokens),
        layer_kind="raster" if not tokens else "vector",
    )


def test_region_payload_maps_into_crop_user_space() -> None:
    page = _raster_page()
    region = (10.0, 80.0, 60.0, 100.0)
    payload: dict[str, list[object]] = {
        "text": ["12"],
        "conf": ["90"],
        "left": [0],
        "top": [0],
        "width": [50],
        "height": [20],
    }
    tokens = tokens_from_tesseract_payload(payload, page, (50, 20), region=region)
    assert len(tokens) == 1
    assert tokens[0].text == "12"
    xs = [point[0] for point in tokens[0].polygon_source]
    ys = [point[1] for point in tokens[0].polygon_source]
    assert min(xs) == pytest.approx(10.0)
    assert max(xs) == pytest.approx(60.0)
    assert min(ys) == pytest.approx(80.0)
    assert max(ys) == pytest.approx(100.0)


def test_expand_user_region_stays_inside_crop() -> None:
    frame = PageFrame(media=(0.0, 0.0, 100.0, 100.0), crop=(0.0, 0.0, 100.0, 100.0), rotate=0)
    polygon = ((0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0))
    region = expand_user_region(polygon, frame)
    assert region is not None
    left, bottom, right, top = region
    assert left >= 0.0
    assert bottom >= 0.0
    assert right <= 100.0
    assert top <= 100.0
    assert right > left
    assert top > bottom
    page = _raster_page()
    payload: dict[str, list[object]] = {
        "text": ["H", "12.5"],
        "conf": ["80", "91"],
        "left": [0, 10],
        "top": [0, 40],
        "width": [20, 30],
        "height": [10, 12],
    }
    tokens = tokens_from_tesseract_payload(payload, page, (100, 100))
    assert len(tokens) == 2
    assert all(item.engine is ExtractionEngine.OCR for item in tokens)
    assert all(item.page == 1 for item in tokens)
    assert all(polygon_in_unit_square(item.polygon_norm) for item in tokens)
    assert tokens[0].text == "H"
    assert tokens[1].text == "12.5"


def test_low_confidence_and_empty_words_are_dropped() -> None:
    page = _raster_page()
    payload: dict[str, list[object]] = {
        "text": ["", "noise", "ok"],
        "conf": ["95", "12", "70"],
        "left": [0, 0, 10],
        "top": [0, 0, 10],
        "width": [10, 10, 10],
        "height": [10, 10, 10],
    }
    tokens = tokens_from_tesseract_payload(payload, page, (100, 100))
    assert [item.text for item in tokens] == ["ok"]


def test_missing_tesseract_leaves_document_untouched() -> None:
    document = extract_pdf_bytes(empty_pdf())
    filled = fill_empty_raster_pages(document, empty_pdf())
    if not raster_pages_need_ocr(document):
        raise AssertionError("пустой PDF должен быть целью OCR")
    # Без бинарника/pytesseract — тот же объект; с ними — не exception.
    assert filled.file_hash == document.file_hash
    assert filled.pages[0].layer_kind == "raster"
    assert filled.pages[0].has_embedded_text is False


def test_rotated_raster_is_not_an_ocr_target() -> None:
    page = _raster_page(rotate=90)
    document = extract_pdf_bytes(empty_pdf())
    fake = PdfDocumentTokens(file_hash=document.file_hash, pages=(page,))
    assert raster_pages_need_ocr(fake) is False


def test_engine_of_marks_pure_ocr_window() -> None:
    polygon = ((0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2))
    ocr = PageToken("12", 1, polygon, polygon, engine=ExtractionEngine.OCR)
    vector = PageToken("12", 1, polygon, polygon)
    assert engine_of((ocr,)) is ExtractionEngine.OCR
    assert engine_of((ocr, vector)) is ExtractionEngine.VECTOR
    assert engine_of((vector,)) is ExtractionEngine.VECTOR


def test_extract_number_keeps_ocr_engine() -> None:
    polygon = ((0.10, 0.40), (0.20, 0.40), (0.20, 0.44), (0.10, 0.44))
    other = ((0.24, 0.40), (0.34, 0.40), (0.34, 0.44), (0.24, 0.44))
    tokens = (
        PageToken("высота", 1, polygon, polygon, engine=ExtractionEngine.OCR),
        PageToken("12", 1, other, other, engine=ExtractionEngine.OCR),
    )
    rule: dict[str, object] = {
        "code": "X-OCR",
        "unit": "м",
        "extractor": {"type": "number", "anchors": ["высота"]},
    }
    hit = extract_number(tokens, rule)
    assert hit is not None
    assert hit.extraction.engine is ExtractionEngine.OCR
    assert hit.extraction.grounded_in_source_tokens is True


def test_ocr_timeout_keeps_parsed_document(monkeypatch: pytest.MonkeyPatch) -> None:
    document = extract_pdf_bytes(empty_pdf())
    monkeypatch.setattr(
        "kontur.application.process_pipeline.tesseract_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "kontur.application.process_pipeline.raster_pages_need_ocr",
        lambda _document: True,
    )

    def _boom(_parser: object, _data: bytes, **_kwargs: object) -> None:
        raise PdfParseTimeoutError("ocr")

    monkeypatch.setattr(
        "kontur.application.process_pipeline.run_pdf_parse_sync",
        _boom,
    )
    assert _maybe_ocr(document, b"%PDF") is document


def test_pipeline_invokes_ocr_helper_when_tesseract_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def _fake_fill(document: object, data: bytes) -> object:
        seen.append(file_sha256(data))
        return document

    monkeypatch.setattr(
        "kontur.application.process_pipeline.tesseract_available",
        lambda: True,
    )
    def _inprocess(parser: object, data: bytes, **_kwargs: object) -> object:
        assert callable(parser)
        return parser(data)

    monkeypatch.setattr(
        "kontur.application.process_pipeline.run_pdf_parse_sync",
        _inprocess,
    )
    monkeypatch.setattr(
        "kontur.application.process_pipeline.fill_empty_raster_pages",
        _fake_fill,
    )
    data = empty_pdf()
    item = PipelineFile(
        file_id="f-empty",
        file_hash=file_sha256(data),
        filename="scan.pdf",
        doc_stage=DocStage.PD,
    )
    report = run_process_pipeline(
        object_id="obj-ocr",
        completeness=_completeness_pd(),
        files=(item,),
        blobs={"f-empty": data},
    )
    assert seen == [file_sha256(data)]
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        item.finding_status for item in report.findings
    }


def test_capabilities_stay_unavailable_regardless_of_tesseract() -> None:
    payload = capabilities_payload()
    engines = {item["name"]: item for item in payload["engines"]}  # type: ignore[misc]
    assert engines["ocr_text"]["status"] == "UNAVAILABLE"
    assert payload["overall"] == "AVAILABLE"


def test_ocr_module_does_not_fork_character_accuracy() -> None:
    assert not hasattr(ocr_tesseract, "character_accuracy")
    assert not hasattr(ocr_tesseract, "wilson_lower")
    assert callable(metrics.character_accuracy)
    assert callable(metrics.wilson)


class _FakeImage:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size

    def resize(self, size: tuple[int, int], _resample: object) -> _FakeImage:
        return _FakeImage(size)


def _patch_ocr_image(
    monkeypatch: pytest.MonkeyPatch,
    size: tuple[int, int],
    reader: object,
) -> None:
    """Подмена Pillow: в CI нет пакета PIL, контракт OCR всё равно проверяется."""

    class _Pillow:
        class Resampling:
            LANCZOS = 1

        @staticmethod
        def open(_data: object) -> _FakeImage:
            return _FakeImage(size)

    monkeypatch.setattr(ocr_tesseract, "tesseract_available", lambda: True)

    def _import(name: str) -> object:
        if name == "pytesseract":
            return reader
        if name == "PIL.Image":
            return _Pillow
        raise AssertionError(name)

    monkeypatch.setattr(ocr_tesseract, "import_module", _import)


def test_empty_single_line_psm_falls_back_to_raw_line(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    class _Tess:
        TesseractError = RuntimeError

        @staticmethod
        def image_to_string(_image: object, lang: str, config: str) -> str:
            seen.append(f"{lang} {config}")
            if "--psm 13" in config and lang == "rus+eng":
                return "внутригородская"
            return ""

    _patch_ocr_image(monkeypatch, (8, 8), _Tess)
    assert ocr_tesseract.ocr_image_bytes(b"png") == "внутригородская"
    assert any("--psm 13" in item for item in seen)
    assert not any("--psm 6" in item for item in seen)


def test_latin_lookalikes_fold_only_near_cyrillic() -> None:
    assert ocr_tesseract.fold_latin_lookalikes("номер AHH организации") == "номер ИНН организации"
    assert ocr_tesseract.fold_latin_lookalikes("дом CTP. далее") == "дом СТР. далее"
    assert ocr_tesseract.fold_latin_lookalikes("ID") == "ID"
    assert ocr_tesseract.fold_latin_lookalikes("GOST 12345") == "GOST 12345"


def test_short_crop_is_scaled_to_40px(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, int]] = []

    class _Tess:
        TesseractError = RuntimeError

        @staticmethod
        def image_to_string(image: object, lang: str, config: str) -> str:
            size = getattr(image, "size", (0, 0))
            seen.append((int(size[0]), int(size[1])))
            return "12" if lang == "rus+eng" and "--psm 7" in config else ""

    _patch_ocr_image(monkeypatch, (80, 16), _Tess)
    assert ocr_tesseract.ocr_image_bytes(b"png") == "12"
    assert seen[0] == (200, 40)


def test_ocr_render_scale_is_300_dpi() -> None:
    assert ocr_tesseract.OCR_RENDER_DPI == 300.0
    assert ocr_tesseract.PDF_USER_DPI == 72.0
    assert ocr_tesseract.RENDER_SCALE == pytest.approx(300.0 / 72.0)
