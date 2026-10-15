"""§13 п.8: ежедневная сверка SHA-256 store ↔ реестр file_hash."""

from __future__ import annotations

import hashlib

import pytest

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.cli import check_storage_integrity as cli
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness
from kontur.infrastructure.db.process_store import MemoryProcessStore, PostgresProcessStore
from kontur.infrastructure.object_store import MemoryObjectStore, object_key
from kontur.infrastructure.storage_integrity import (
    RegistryFile,
    check_storage_integrity,
    registry_from_memory,
    registry_from_store,
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


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _PgConn:
    """Фейк psycopg-соединения: проверяем SQL и маппинг, не живой PG."""

    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows
        self.sql: list[str] = []

    def execute(self, sql: str, params: object = None) -> _Cursor:
        self.sql.append(sql)
        return _Cursor(self.rows)


def test_postgres_list_all_files_selects_registry_and_strips_char_padding() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    conn = _PgConn([("p1", "f1", digest + "  "), ("p1", "f2", None), ("p2", "f1", "")])
    rows = PostgresProcessStore(conn).list_all_files()
    assert "FROM process_files" in conn.sql[0] and "WHERE" not in conn.sql[0]
    assert rows == [("p1", "f1", digest), ("p1", "f2", ""), ("p2", "f1", "")]
    entries = registry_from_store(PostgresProcessStore(conn))
    assert [e.expected_hash for e in entries] == [digest, "", ""]
    report = check_storage_integrity(entries, MemoryObjectStore())
    assert report.bad == 3
    assert {f.status for f in report.findings if not f.expected_hash} == {"no_hash"}


class _FakePgLikeStore:
    """list_all_files + save_audit_event, как у Postgres-стора (без живого PG)."""

    def __init__(self, rows: list[tuple[str, str, str]]) -> None:
        self.rows = rows
        self.audit: list[tuple[str, str, str, dict[str, object]]] = []

    def list_all_files(self) -> list[tuple[str, str, str]]:
        return self.rows

    def save_audit_event(
        self, process_id: str, actor_id: str, action: str, payload: dict[str, object]
    ) -> None:
        self.audit.append((process_id, actor_id, action, payload))


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "KONTUR_INTEGRITY_ALLOW_EMPTY",
        "KONTUR_DB_URL",
        "KONTUR_OBJECT_STORE_URL",
        "KONTUR_S3_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_cli_ok_mismatch_audit_and_empty_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    blobs = MemoryObjectStore()
    blobs.put("p1", "f1", b"good")
    good = hashlib.sha256(b"good").hexdigest()
    store = _FakePgLikeStore([("p1", "f1", good)])
    assert cli.run(store, blobs) == cli.EXIT_OK
    assert store.audit == []

    blobs.put("p1", "f1", b"evil")
    assert cli.run(store, blobs) == cli.EXIT_MISMATCH
    assert store.audit[0][0] == "p1"
    assert store.audit[0][2] == "STORAGE_INTEGRITY_MISMATCH"

    nohash = _FakePgLikeStore([("p1", "f1", "")])
    assert cli.run(nohash, blobs) == cli.EXIT_MISMATCH
    assert nohash.audit[0][3]["status"] == "no_hash"


def test_cli_zero_files_fail_closed_with_explicit_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)
    store = _FakePgLikeStore([])
    assert cli.run(store, MemoryObjectStore()) == cli.EXIT_EMPTY
    monkeypatch.setenv("KONTUR_INTEGRITY_ALLOW_EMPTY", "1")
    assert cli.run(store, MemoryObjectStore()) == cli.EXIT_OK


def test_cli_db_without_object_store_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("KONTUR_DB_URL", "postgresql://u:p@127.0.0.1:1/x")
    assert cli.run() == cli.EXIT_NO_OBJECT_STORE


def test_cli_registry_unavailable_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)

    class _Broken:
        def list_all_files(self) -> list[tuple[str, str, str]]:
            raise RuntimeError("db down")

    assert cli.run(_Broken(), MemoryObjectStore()) == cli.EXIT_UNAVAILABLE


def test_cli_default_in_memory_registry_is_empty_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    assert cli.main() == cli.EXIT_EMPTY
    monkeypatch.setenv("KONTUR_INTEGRITY_ALLOW_EMPTY", "1")
    assert cli.main() == cli.EXIT_OK


def test_memory_list_all_files_matches_registry() -> None:
    meta = MemoryProcessStore()
    ws = ProcessWorkspace(store=meta, objects=MemoryObjectStore())
    record = ws.create("obj-list", _completeness())
    digest = hashlib.sha256(b"q").hexdigest()
    assert ws.attach_file(
        record,
        AcceptedFile(
            file_id="fq",
            file_hash=digest,
            filename="q.pdf",
            doc_stage=DocStage.PD,
            size_bytes=1,
        ),
    )
    assert meta.list_all_files() == [(record.process_id, "fq", digest)]


class _FlakyObjects:
    """Один файл бросает (как S3 5xx), остальные читаются; без iter_chunks → путь get()."""

    def __init__(self, bodies: dict[str, bytes], broken: set[str]) -> None:
        self.bodies = bodies
        self.broken = broken

    def get(self, process_id: str, file_id: str) -> bytes | None:
        if file_id in self.broken:
            raise OSError("s3 down")
        return self.bodies.get(file_id)


def test_read_error_on_one_file_does_not_mask_other_findings() -> None:
    good = hashlib.sha256(b"a").hexdigest()
    entries = (
        RegistryFile("p", "boom", good),
        RegistryFile("p", "flip", good),
        RegistryFile("p", "fine", good),
        RegistryFile("p", "gone", good),
    )
    objects = _FlakyObjects({"flip": b"zzz", "fine": b"a"}, {"boom"})
    report = check_storage_integrity(entries, objects)  # type: ignore[arg-type]
    status = {f.file_id: f.status for f in report.findings}
    assert status == {"boom": "error", "flip": "mismatch", "fine": "ok", "gone": "missing"}
    assert (report.ok, report.bad) == (1, 3)


def test_audit_exception_does_not_abort_run_or_mask_mismatches() -> None:
    good = hashlib.sha256(b"a").hexdigest()
    blobs = MemoryObjectStore()
    blobs.put("p", "f1", b"x")
    blobs.put("p", "f2", b"y")
    calls: list[str] = []

    def boom(_a: str, _b: str, payload: dict[str, object]) -> None:
        calls.append(str(payload["file_id"]))
        raise RuntimeError("audit db down")

    report = check_storage_integrity(
        (RegistryFile("p", "f1", good), RegistryFile("p", "f2", good)), blobs, audit=boom
    )
    assert calls == ["f1", "f2"]  # второй файл проверен и после сбоя audit
    assert [f.status for f in report.findings] == ["mismatch", "mismatch"]
    assert not report.passed


def test_cli_audit_failure_still_exit_1_not_5(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)

    class _Store(_FakePgLikeStore):
        def save_audit_event(self, *a: object, **k: object) -> None:
            raise RuntimeError("audit down")

    blobs = MemoryObjectStore()
    blobs.put("p1", "f1", b"evil")
    store = _Store([("p1", "f1", hashlib.sha256(b"good").hexdigest())])
    assert cli.run(store, blobs) == cli.EXIT_MISMATCH


def test_streaming_hash_matches_for_multi_chunk_blob() -> None:
    body = b"0123456789" * 300_000  # 3 MB > CHUNK_SIZE (1 MiB)
    blobs = MemoryObjectStore()
    blobs.put("p", "big", body)
    entry = RegistryFile("p", "big", hashlib.sha256(body).hexdigest())
    assert check_storage_integrity((entry,), blobs).passed
    chunks = blobs.iter_chunks("p", "big", 1 << 20)
    assert chunks is not None and len(list(chunks)) == 3


def test_uppercase_pg_hash_is_normalised_and_matches() -> None:
    digest = hashlib.sha256(b"x").hexdigest()
    conn = _PgConn([("p1", "f1", digest.upper() + " ")])
    entries = registry_from_store(PostgresProcessStore(conn))
    blobs = MemoryObjectStore()
    blobs.put("p1", "f1", b"x")
    assert entries[0].expected_hash == digest
    assert check_storage_integrity(entries, blobs).passed


def test_non_hex_or_short_pg_hash_is_invalid_hash_not_silent() -> None:
    conn = _PgConn([("p1", "f1", "z" * 64), ("p1", "f2", "abc123")])
    entries = registry_from_store(PostgresProcessStore(conn))
    blobs = MemoryObjectStore()
    blobs.put("p1", "f1", b"x")
    blobs.put("p1", "f2", b"x")
    report = check_storage_integrity(entries, blobs)
    assert [f.status for f in report.findings] == ["invalid_hash", "invalid_hash"]
    assert report.bad == 2


def test_cli_does_not_duplicate_audit_for_unchanged_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch)
    meta = MemoryProcessStore()
    blobs = MemoryObjectStore()
    ws = ProcessWorkspace(store=meta, objects=blobs)
    record = ws.create("obj-dedup", _completeness())
    digest = hashlib.sha256(b"orig").hexdigest()
    assert ws.attach_file(
        record,
        AcceptedFile(
            file_id="fd",
            file_hash=digest,
            filename="d.pdf",
            doc_stage=DocStage.PD,
            size_bytes=4,
        ),
    )
    blobs.put(record.process_id, "fd", b"evil")
    for _ in range(3):  # три ежедневных прогона
        assert cli.run(meta, blobs) == cli.EXIT_MISMATCH
    assert len(meta.load_audit(record.process_id)) == 1
    blobs.put(record.process_id, "fd", b"evil2")  # состояние изменилось → новая запись
    assert cli.run(meta, blobs) == cli.EXIT_MISMATCH
    assert len(meta.load_audit(record.process_id)) == 2
