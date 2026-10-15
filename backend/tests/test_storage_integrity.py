"""§13 п.8: ежедневная сверка SHA-256 store ↔ реестр file_hash."""

from __future__ import annotations

import hashlib

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness
from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.object_store import MemoryObjectStore, object_key
from kontur.infrastructure.storage_integrity import (
    RegistryFile,
    check_storage_integrity,
    registry_from_memory,
)


def _completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def test_integrity_ok_when_blob_matches_registry() -> None:
    meta = MemoryProcessStore()
    blobs = MemoryObjectStore()
    ws = ProcessWorkspace(store=meta, objects=blobs)
    record = ws.create("obj-ok", _completeness())
    body = b"%PDF-1.4 integrity-ok"
    digest = hashlib.sha256(body).hexdigest()
    item = AcceptedFile(
        file_id="f1",
        file_hash=digest,
        filename="a.pdf",
        doc_stage=DocStage.PD,
        size_bytes=len(body),
    )
    assert ws.attach_file(record, item)
    ws.keep_blob(record, "f1", body)

    report = check_storage_integrity(registry_from_memory(meta), blobs)
    assert report.passed
    assert report.ok == 1
    assert report.bad == 0


def test_integrity_detects_byte_flip() -> None:
    meta = MemoryProcessStore()
    blobs = MemoryObjectStore()
    ws = ProcessWorkspace(store=meta, objects=blobs)
    record = ws.create("obj-flip", _completeness())
    body = b"%PDF-1.4 integrity-flip"
    digest = hashlib.sha256(body).hexdigest()
    item = AcceptedFile(
        file_id="f-flip",
        file_hash=digest,
        filename="b.pdf",
        doc_stage=DocStage.PD,
        size_bytes=len(body),
    )
    assert ws.attach_file(record, item)
    ws.keep_blob(record, "f-flip", body)
    # Подмена байта в store после регистрации эталона.
    flipped = bytearray(body)
    flipped[-1] = (flipped[-1] + 1) % 256
    blobs.put(record.process_id, "f-flip", bytes(flipped))

    audits: list[tuple[str, str, dict[str, object]]] = []
    report = check_storage_integrity(
        registry_from_memory(meta),
        blobs,
        audit=lambda actor, action, payload: audits.append((actor, action, payload)),
    )
    assert not report.passed
    assert report.bad >= 1
    bad = [f for f in report.findings if f.status == "mismatch"]
    assert bad
    assert bad[0].expected_hash == digest
    assert bad[0].actual_hash != digest
    assert audits and audits[0][1] == "STORAGE_INTEGRITY_MISMATCH"


def test_integrity_missing_blob() -> None:
    entries = (
        RegistryFile(
            process_id="p-miss",
            file_id="gone",
            expected_hash=hashlib.sha256(b"x").hexdigest(),
        ),
    )
    report = check_storage_integrity(entries, MemoryObjectStore())
    assert not report.passed
    assert report.bad == 1
    assert report.findings[0].status == "missing"
    assert report.findings[0].actual_hash is None


def test_registry_from_memory_reads_file_hash() -> None:
    meta = MemoryProcessStore()
    blobs = MemoryObjectStore()
    ws = ProcessWorkspace(store=meta, objects=blobs)
    record = ws.create("obj-reg", _completeness())
    body = b"reg-bytes"
    digest = hashlib.sha256(body).hexdigest()
    assert ws.attach_file(
        record,
        AcceptedFile(
            file_id="f-reg",
            file_hash=digest,
            filename="c.pdf",
            doc_stage=DocStage.PD,
            size_bytes=len(body),
        ),
    )
    ws.keep_blob(record, "f-reg", body)
    rows = registry_from_memory(meta)
    assert any(r.file_id == "f-reg" and r.expected_hash == digest for r in rows)
    assert object_key(record.process_id, "f-reg") == f"{record.process_id}/f-reg"


def test_empty_file_hash_is_not_silently_skipped() -> None:
    entries = (RegistryFile(process_id="p-nh", file_id="f-nh", expected_hash=""),)
    audits: list[str] = []
    report = check_storage_integrity(
        entries,
        MemoryObjectStore(),
        audit=lambda _a, action, _p: audits.append(action),
    )
    assert not report.passed
    assert report.findings[0].status == "no_hash"
    assert audits == ["STORAGE_INTEGRITY_MISMATCH"]


def test_cli_empty_registry_is_fail_closed(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "check_storage_integrity.py"
    spec = importlib.util.spec_from_file_location("check_storage_integrity_cli", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("KONTUR_INTEGRITY_ALLOW_EMPTY", raising=False)
    monkeypatch.delenv("KONTUR_DB_URL", raising=False)
    assert mod.main() == 3
    monkeypatch.setenv("KONTUR_INTEGRITY_ALLOW_EMPTY", "1")
    assert mod.main() == 0
