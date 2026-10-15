"""P0: тела файлов переживают «рестарт» workspace при общем ObjectStore."""

from __future__ import annotations

import hashlib

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness
from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.object_store import MemoryObjectStore, object_key


def _completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def test_object_key_shape() -> None:
    assert object_key("p1", "f1") == "p1/f1"


def test_memory_object_store_roundtrip() -> None:
    store = MemoryObjectStore()
    key = store.put("proc-a", "file-1", b"%PDF-1.4 durable")
    assert key == "proc-a/file-1"
    assert store.get("proc-a", "file-1") == b"%PDF-1.4 durable"
    assert store.get("proc-a", "missing") is None


def test_blobs_survive_workspace_restart_same_object_store() -> None:
    """Новый ProcessWorkspace + тот же store/objects = после рестарта API."""

    shared_meta = MemoryProcessStore()
    shared_blobs = MemoryObjectStore()
    first = ProcessWorkspace(store=shared_meta, objects=shared_blobs)
    record = first.create("obj-durable", _completeness())
    png = b"\x89PNG\r\n\x1a\n" + b"fake-raster-payload-for-sha"
    digest = hashlib.sha256(png).hexdigest()
    item = AcceptedFile(
        file_id="f-png",
        file_hash=digest,
        filename="sheet.png",
        doc_stage=DocStage.PD,
        size_bytes=len(png),
    )
    assert first.attach_file(record, item)
    first.keep_blob(record, "f-png", png)
    process_id = record.process_id
    assert first.get_blob(record, "f-png") == png
    expected = hashlib.sha256(png).hexdigest()

    # «Рестарт»: новый workspace, те же бэкенды; in-memory cache пуст.
    second = ProcessWorkspace(store=shared_meta, objects=shared_blobs)
    restored = second.get(process_id)
    assert restored is not None
    body = second.get_blob(restored, "f-png")
    assert body is not None
    assert hashlib.sha256(body).hexdigest() == expected
    assert body == png
    assert any(f.file_id == "f-png" and f.file_path == f"{process_id}/f-png" for f in restored.files)


def test_wiring_defaults_to_memory(monkeypatch) -> None:
    monkeypatch.delenv("KONTUR_DB_URL", raising=False)
    monkeypatch.delenv("KONTUR_OBJECT_STORE_URL", raising=False)
    monkeypatch.delenv("KONTUR_S3_ENDPOINT", raising=False)
    from kontur.application.wiring import build_object_store, build_process_store, build_workspace
    from kontur.infrastructure.db.process_store import MemoryProcessStore
    from kontur.infrastructure.object_store import MemoryObjectStore

    assert isinstance(build_process_store(), MemoryProcessStore)
    assert isinstance(build_object_store(), MemoryObjectStore)
    ws = build_workspace()
    assert isinstance(ws._store, MemoryProcessStore)
    assert isinstance(ws._objects, MemoryObjectStore)
