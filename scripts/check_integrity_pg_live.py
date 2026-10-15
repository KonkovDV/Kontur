"""Live PostgreSQL proof for §13 п.8 integrity job (list_all_files, audit, fail-closed).

Запускается в CI (workflow sync-lifecycle-db, сервис postgres) после schema.sql.
Локально без Postgres не выполняется — это единственное PG-доказательство.
"""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import psycopg

from kontur.cli.check_storage_integrity import (
    EXIT_EMPTY,
    EXIT_MISMATCH,
    EXIT_NO_OBJECT_STORE,
    EXIT_OK,
    run,
)
from kontur.domain.models import DocStage
from kontur.domain.statuses import ProcessState, Scenario
from kontur.infrastructure.db.connecting_store import ConnectingPostgresProcessStore
from kontur.infrastructure.db.process_store import (
    FileRecord,
    PostgresProcessStore,
    ProcessSnapshot,
)
from kontur.infrastructure.object_store import MemoryObjectStore

DSN = os.environ.get("KONTUR_DB_URL", "postgresql://postgres:postgres@localhost:5432/kontur")


def _expect(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected exit {expected}, got {actual}")
    print(f"ok: {label} -> exit {actual}")


def main() -> None:
    os.environ["KONTUR_DB_URL"] = DSN
    for name in ("KONTUR_INTEGRITY_ALLOW_EMPTY",):
        os.environ.pop(name, None)
    suffix = uuid4().hex[:10]
    pid = f"integrity-live-{suffix}"
    bodies = {"f1": b"%PDF integrity live one", "f2": b"%PDF integrity live two"}
    files = tuple(
        FileRecord(
            file_id=fid,
            file_hash=hashlib.sha256(body).hexdigest(),
            filename=f"{fid}.pdf",
            doc_stage=stage,
            size_bytes=len(body),
        )
        for (fid, body), stage in zip(bodies.items(), (DocStage.PD, DocStage.RD), strict=True)
    )
    snap = ProcessSnapshot(
        process_id=pid,
        object_id=f"integrity-obj-{suffix}",
        process_state=ProcessState.PARSING,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        files=files,
    )
    with psycopg.connect(DSN, autocommit=True) as connection:
        PostgresProcessStore(connection).save(snap)

    store = ConnectingPostgresProcessStore(DSN)
    rows = store.list_all_files()
    if sorted(r[1] for r in rows if r[0] == pid) != ["f1", "f2"]:
        raise AssertionError(f"list_all_files wrong: {rows}")

    objects = MemoryObjectStore()
    for fid, body in bodies.items():
        objects.put(pid, fid, body)
    _expect(run(store, objects), EXIT_OK, "pg registry matches blobs")

    # CLI default path: store is built from KONTUR_DB_URL by wiring (former P0: always exit 2).
    os.environ["KONTUR_OBJECT_STORE_URL"] = "http://object-store.invalid"
    try:
        _expect(run(objects=objects), EXIT_OK, "pg env-wired registry (CLI default path)")
    finally:
        os.environ.pop("KONTUR_OBJECT_STORE_URL", None)

    objects.put(pid, "f2", b"%PDF tampered!!!!!!!!!!!")
    _expect(run(store, objects), EXIT_MISMATCH, "pg byte flip")
    with psycopg.connect(DSN, autocommit=True) as connection:
        n = connection.execute(
            "SELECT count(*) FROM audit_log WHERE process_id=%s "
            "AND action='STORAGE_INTEGRITY_MISMATCH'",
            (pid,),
        ).fetchone()
    if n is None or int(n[0]) < 1:
        raise AssertionError("no STORAGE_INTEGRITY_MISMATCH audit_log row on PG path")
    print("ok: audit_log row written on PG path")

    objects.put(pid, "f2", bodies["f2"])
    with psycopg.connect(DSN, autocommit=True) as connection:
        connection.execute(
            "UPDATE process_files SET file_hash='' WHERE process_id=%s AND file_id='f1'", (pid,)
        )
    _expect(run(store, objects), EXIT_MISMATCH, "pg empty file_hash is not skipped")

    # DB без object store -> fail-closed (store/objects не переданы -> wiring по env)
    for name in ("KONTUR_OBJECT_STORE_URL", "KONTUR_S3_ENDPOINT"):
        os.environ.pop(name, None)
    _expect(run(), EXIT_NO_OBJECT_STORE, "pg without object store")

    with psycopg.connect(DSN, autocommit=True) as connection:
        connection.execute("DELETE FROM process_files")
    _expect(run(store, objects), EXIT_EMPTY, "pg 0 files")
    print("check_integrity_pg_live: PASS")


if __name__ == "__main__":
    main()
