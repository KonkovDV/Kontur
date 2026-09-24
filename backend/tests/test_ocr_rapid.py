"""Веса RapidOCR: замок и отказ от сети. Статус ocr_text не меняется."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kontur.domain.capabilities import CapStatus, declared_capabilities
from kontur.infrastructure import ocr_rapid
from kontur.infrastructure.ocr_rapid import weights_ready

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
