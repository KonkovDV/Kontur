"""Live PostgreSQL proof for relay retries and manual recovery."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg

from kontur.application.protocol import protocol_identity
from kontur.domain.statuses import ProcessState, Scenario
from kontur.infrastructure.db.process_store import (
    PostgresProcessStore,
    ProcessSnapshot,
)
from kontur.infrastructure.outbox import RETRY_SECONDS, RecordingPublisher
from kontur.infrastructure.sync_relay import (
    relay_once_postgres_with_sync,
    retry_failed_sync,
)

DSN = os.environ.get(
    "KONTUR_DB_URL",
    "postgresql://postgres:postgres@localhost:5432/kontur",
)


def _payload(process_id: str, object_id: str) -> dict[str, object]:
    return {
        "protocol_id": protocol_identity(process_id, 1),
        "object_id": object_id,
        "version": 1,
        "status": "PROTOCOL_FINALIZED",
        "scenario": "SINGLE_ONLY",
        "upload_status": {
            "pd": "PD_MISSING",
            "rd": "RD_MISSING",
            "id": "ID_MISSING",
        },
        "sections": {
            "completeness": [],
            "candidates": [],
            "confirmed": [],
            "negative_verified": [],
            "suspicions": [],
            "missing_evidence": [],
            "preliminary_no_difference": [],
        },
        "violation_count": 0,
        "versions": {
            "matrix_version": "draft-0",
            "model_version": "none",
            "dataset_version": "sync-lifecycle-live-v1",
        },
        "input_manifest": {"manifest_hash": "sync-lifecycle", "files": []},
    }


def _setup(process_id: str, object_id: str) -> None:
    protocol_id = protocol_identity(process_id, 1)
    base = ProcessSnapshot(
        process_id=process_id,
        object_id=object_id,
        process_state=ProcessState.COMPLETED,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        dataset_version="sync-lifecycle-live-v1",
        input_manifest_hash="sync-lifecycle",
    )
    final = ProcessSnapshot(
        process_id=process_id,
        object_id=object_id,
        process_state=ProcessState.FINALIZED,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        dataset_version="sync-lifecycle-live-v1",
        input_manifest_hash="sync-lifecycle",
        finalized_by="inspector-live",
        protocol_id=protocol_id,
    )
    with psycopg.connect(DSN, autocommit=True) as connection:
        store = PostgresProcessStore(connection)
        store.save(base)
        store.materialize_finalized(final, _payload(process_id, object_id))


def _state(process_id: str) -> tuple[str, int, str | None, str, int]:
    with psycopg.connect(DSN, autocommit=True) as connection:
        row = connection.execute(
            """SELECT p.sync_state, p.sync_attempts, p.last_error_code,
                      o.status, o.attempts
                 FROM processes p
                 JOIN integration_outbox o ON o.process_id = p.id
                WHERE p.id = %s""",
            (process_id,),
        ).fetchone()
    if row is None:
        raise AssertionError("sync state row missing")
    error = None if row[2] is None else str(row[2])
    return str(row[0]), int(row[1]), error, str(row[3]), int(row[4])


def main() -> None:
    suffix = uuid4().hex[:12]
    process_id = f"sync-live-{suffix}"
    object_id = f"sync-object-{suffix}"
    _setup(process_id, object_id)
    now = datetime.now(tz=UTC) + timedelta(seconds=1)

    for index, delay in enumerate(RETRY_SECONDS, start=1):
        with psycopg.connect(DSN) as connection:
            result = relay_once_postgres_with_sync(
                connection,
                RecordingPublisher(fail_remaining=1),
                now,
            )
        if result != "PENDING":
            raise AssertionError(f"attempt {index}: expected PENDING, got {result}")
        state = _state(process_id)
        if state[0] != "RETRY_WAIT" or state[1] != index or state[3] != "PENDING":
            raise AssertionError(f"attempt {index}: invalid state {state}")
        now += timedelta(seconds=delay)

    with psycopg.connect(DSN) as connection:
        result = relay_once_postgres_with_sync(
            connection,
            RecordingPublisher(fail_remaining=1),
            now,
        )
    if result != "FAILED_TERMINAL":
        raise AssertionError(f"expected FAILED_TERMINAL, got {result}")
    state = _state(process_id)
    if state[0] != "PENDING_SYNC" or state[1] != 4 or state[3] != "FAILED_TERMINAL":
        raise AssertionError(f"exhaustion did not preserve manual retry: {state}")

    with psycopg.connect(DSN) as connection:
        retry_failed_sync(connection, process_id, "admin-live", now + timedelta(seconds=1))
    state = _state(process_id)
    if state[0] != "PENDING_SYNC" or state[1] != 0 or state[3] != "PENDING":
        raise AssertionError(f"manual retry did not reset state: {state}")

    with psycopg.connect(DSN, autocommit=True) as connection:
        audit_count = connection.execute(
            """SELECT count(*) FROM audit_log
                WHERE process_id = %s
                  AND action IN ('SYNC_RETRY_EXHAUSTED', 'SYNC_MANUAL_RETRY')""",
            (process_id,),
        ).fetchone()
    if audit_count is None or int(audit_count[0]) != 2:
        raise AssertionError(f"expected two sync audit events, got {audit_count}")
    print("live PostgreSQL sync lifecycle checks passed")


if __name__ == "__main__":
    main()
