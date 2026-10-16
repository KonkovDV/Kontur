"""P0: тела файлов переживают «рестарт» workspace при общем ObjectStore."""

from __future__ import annotations

import hashlib

import pytest

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
    assert any(
        f.file_id == "f-png" and f.file_path == f"{process_id}/f-png" for f in restored.files
    )


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


def test_wiring_fails_db_without_object_store_in_production(monkeypatch) -> None:
    monkeypatch.setenv("KONTUR_ENV", "production")
    monkeypatch.setenv("KONTUR_DB_URL", "postgresql://kontur:kontur@localhost/kontur")
    monkeypatch.delenv("KONTUR_OBJECT_STORE_URL", raising=False)
    monkeypatch.delenv("KONTUR_S3_ENDPOINT", raising=False)
    from kontur.application.wiring import build_workspace

    try:
        build_workspace()
    except RuntimeError as exc:
        assert "иллюзия durable" in str(exc) or "OBJECT_STORE" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for DB without object store")


def test_wiring_allows_db_without_object_store_in_dev(monkeypatch) -> None:
    pytest.importorskip("psycopg")
    monkeypatch.setenv("KONTUR_ENV", "dev")
    monkeypatch.setenv("KONTUR_DB_URL", "postgresql://kontur:kontur@localhost/kontur")
    monkeypatch.delenv("KONTUR_OBJECT_STORE_URL", raising=False)
    monkeypatch.delenv("KONTUR_S3_ENDPOINT", raising=False)
    monkeypatch.setattr(
        "kontur.infrastructure.db.migrations.apply_migrations_dsn", lambda dsn: None
    )
    from kontur.application.wiring import build_workspace
    from kontur.infrastructure.db.connecting_store import ConnectingPostgresProcessStore
    from kontur.infrastructure.object_store import MemoryObjectStore

    ws = build_workspace()
    assert isinstance(ws._store, ConnectingPostgresProcessStore)
    assert isinstance(ws._objects, MemoryObjectStore)


def test_expanded_keep_blob_sets_file_path_after_append() -> None:
    """Regression: keep_blob после append — file_path на expanded в метаданных."""

    from unittest.mock import patch

    from kontur.application.process_pipeline import PipelineFile, PipelineReport

    shared_meta = MemoryProcessStore()
    shared_blobs = MemoryObjectStore()
    ws = ProcessWorkspace(store=shared_meta, objects=shared_blobs)
    record = ws.create("obj-exp", _completeness())
    zip_bytes = b"PK\x03\x04-fake-zip"
    zip_item = AcceptedFile(
        file_id="f-zip",
        file_hash=hashlib.sha256(zip_bytes).hexdigest(),
        filename="pack.zip",
        doc_stage=DocStage.PD,
        size_bytes=len(zip_bytes),
    )
    assert ws.attach_file(record, zip_item)
    ws.keep_blob(record, "f-zip", zip_bytes)

    expanded_id = "f-zip__1"
    pdf = b"%PDF-1.4 expanded-page"
    report = PipelineReport(
        findings=(),
        rules_evaluated=0,
        parse_errors=(),
        pages_built=0,
        stamp_by_file_id={},
        phase_seconds={"parse": 0.0, "compare": 0.0},
        expanded_files=(
            PipelineFile(
                file_id=expanded_id,
                file_hash=hashlib.sha256(pdf).hexdigest(),
                filename="sheet.pdf",
                doc_stage=DocStage.PD,
            ),
        ),
        expanded_blobs={expanded_id: pdf},
    )

    with patch("kontur.application.runtime.run_process_pipeline", return_value=report):
        # PARSING → run_matrix_pipeline advances; create leaves CREATED/PARSING?
        from kontur.domain.statuses import ProcessState

        record.process_state = ProcessState.PARSING
        ws.run_matrix_pipeline(record)

    paths = {f.file_id: f.file_path for f in record.files}
    assert expanded_id in paths
    assert paths[expanded_id] == f"{record.process_id}/{expanded_id}"
    assert ws.get_blob(record, expanded_id) == pdf
