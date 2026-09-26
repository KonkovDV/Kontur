"""Веса RapidOCR: замок и отказ от сети. Статус ocr_text не меняется."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kontur.domain.capabilities import CapStatus, declared_capabilities
from kontur.domain.coordinates import PageFrame
from kontur.infrastructure import ocr_rapid
from kontur.infrastructure.ocr_rapid import weights_ready
from kontur.infrastructure.pdfium_tokens import PdfPageTokens

_INFRA = Path(__file__).resolve().parents[1] / "src" / "kontur" / "infrastructure"
LOCK = _INFRA / "ocr_weights.lock.json"
SOURCE = Path(ocr_rapid.__file__).read_text(encoding="utf-8")


def test_lock_pins_eslav_weights() -> None:
    payload = json.loads(LOCK.read_text(encoding="utf-8"))
    assert payload["runtime_download"] is False
    roles = {item["role"]: item for item in payload["files"]}
    assert set(roles) == {"det", "rec", "cls", "dict"}
    assert roles["rec"]["name"] == "eslav_PP-OCRv5_rec_mobile.onnx"
    assert roles["rec"]["sha256"] == (
        "08705d6721849b1347d26187f15a5e362c431963a2a62bfff4feac578c489aab"
    )
    for item in roles.values():
        assert len(item["sha256"]) == 64
        int(item["sha256"], 16)


def test_runtime_module_does_not_download() -> None:
    assert "urlopen" not in SOURCE
    assert "urlretrieve" not in SOURCE
    assert "modelscope" not in SOURCE


def test_missing_catalog_is_not_ready(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv(ocr_rapid.WEIGHTS_ENV, raising=False)
    weights_ready.cache_clear()
    ocr_rapid._engine.cache_clear()
    assert weights_ready() is False


def test_hash_mismatch_is_not_ready(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = json.loads(LOCK.read_text(encoding="utf-8"))
    for item in payload["files"]:
        target = tmp_path / item["name"]
        target.write_bytes(b"not-the-weight")
        assert hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]
    monkeypatch.setenv(ocr_rapid.WEIGHTS_ENV, str(tmp_path))
    weights_ready.cache_clear()
    assert weights_ready() is False


def test_ocr_text_stays_measured() -> None:
    engines = {item.name: item.status for item in declared_capabilities()}
    assert engines["ocr_text"] is CapStatus.MEASURED


class _Member:
    def __init__(self, name: str) -> None:
        self.name = name


class _Enum:
    def __init__(self, *names: str) -> None:
        for name in names:
            setattr(self, name, _Member(name))


class _RapidModule:
    EngineType = _Enum("ONNXRUNTIME")
    OCRVersion = _Enum("PPOCRV5")
    ModelType = _Enum("MOBILE")
    LangRec = _Enum("ESLAV")


def test_engine_params_pass_rapidocr_enums_not_strings() -> None:
    paths = {role: Path(f"/w/{role}") for role in ("det", "rec", "cls", "dict")}
    params = ocr_rapid._engine_params(_RapidModule(), paths)
    for stage in ("Det", "Cls", "Rec"):
        assert params[f"{stage}.engine_type"] is _RapidModule.EngineType.ONNXRUNTIME
        assert params[f"{stage}.ocr_version"] is _RapidModule.OCRVersion.PPOCRV5
    assert params["Rec.lang_type"] is _RapidModule.LangRec.ESLAV
    assert params["Rec.rec_keys_path"] == str(paths["dict"])


def test_line_text_without_engine_is_empty(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(ocr_rapid, "_engine", lambda: None)
    assert ocr_rapid.rapid_available() is False
    assert ocr_rapid.rapid_line_text(b"\x89PNG") == ""


def test_pilot_refuses_eslav_without_weights(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from kontur.evaluation import ocr_pilot

    monkeypatch.setattr(ocr_rapid, "_engine", lambda: None)
    monkeypatch.setenv(ocr_pilot.OCR_PILOT_ENGINE_ENV, "eslav")
    assert ocr_pilot.main() == 3
    monkeypatch.setenv(ocr_pilot.OCR_PILOT_ENGINE_ENV, "vlm")
    assert ocr_pilot.main() == 2


class _LineResult:
    txts = ("1200 мм",)
    scores = (0.93,)


def test_value_crop_is_one_line_without_detector(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[dict[str, object]] = []

    def engine(image: object, **kwargs: object) -> _LineResult:
        calls.append(kwargs)
        return _LineResult()

    monkeypatch.setattr(ocr_rapid, "_engine", lambda: engine)
    page = PdfPageTokens(
        page=1,
        frame=PageFrame(media=(0.0, 0.0, 80.0, 20.0), crop=(0.0, 0.0, 80.0, 20.0)),
        tokens=(),
        has_embedded_text=False,
        layer_kind="raster",
    )
    tokens = ocr_rapid.rapid_crop_tokens(object(), page, (80, 20))
    assert tokens is not None
    assert [token.text for token in tokens] == ["1200 мм"]
    assert calls == [{"use_det": False, "use_cls": False, "use_rec": True}]
