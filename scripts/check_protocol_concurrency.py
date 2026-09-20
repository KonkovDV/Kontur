"""Live PostgreSQL race checks for atomic protocol materialization.

This is an executable CI check, not a mock. It covers two failure modes:

* two identical finalize deliveries for one process are idempotent;
* two processes racing for the same object/version cannot both commit.

RabbitMQ/Rin delivery is deliberately out of scope. The check only proves the
PostgreSQL transaction, immutable protocol and outbox boundary from ADR-0009.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg

from kontur.application.protocol import protocol_identity
from kontur.domain.statuses import ProcessState, Scenario
from kontur.infrastructure.db.process_store import (
    PostgresProcessStore,
    ProcessSnapshot,
    ProtocolConflictError,
    protocol_payload_sha256,
)

DSN = os.environ.get(
    "KONTUR_DB_URL",
    "postgresql://postgres:postgres@localhost:5432/kontur",
)


def _snapshot(
    *, process_id: str, object_id: str, state: ProcessState, protocol_id: str | None = None
) -> ProcessSnapshot:
    return ProcessSnapshot(
        process_id=process_id,
        object_id=object_id,
        process_state=state,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        dataset_version="live-db-race-v1",
        finalized_by="inspector-race" if state is ProcessState.FINALIZED else None,
        protocol_id=protocol_id,
        input_manifest_hash="race-manifest",
    )


def _payload(*, process_id: str, object_id: str, version: int) -> dict[str, object]:
    protocol_id = protocol_identity(process_id, version)
    return {
        "protocol_id": protocol_id,
        "object_id": object_id,
        "version": version,
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
            "dataset_version": "live-db-race-v1",
            "git_sha": os.environ.get("GITHUB_SHA", "local"),
        },
        "input_manifest": {"manifest_hash": "race-manifest", "files": []},
    }


def _connect() -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(DSN, autocommit=True)


def _prepare(process_id: str, object_id: str) -> None:
    with _connect() as connection:
        PostgresProcessStore(connection).save(
            _snapshot(process_id=process_id, object_id=object_id, state=ProcessState.COMPLETED)
        )


def _finalize(
    *, process_id: str, object_id: str, version: int, barrier: Barrier
) -> str:
    protocol_id = protocol_identity(process_id, version)
    snapshot = _snapshot(
        process_id=process_id,
        object_id=object_id,
        state=ProcessState.FINALIZED,
        protocol_id=protocol_id,
    )
    payload = _payload(process_id=process_id, object_id=object_id, version=version)
    barrier.wait(timeout=15)
    try:
        with _connect() as connection:
            PostgresProcessStore(connection).materialize_finalized(snapshot, payload)
    except ProtocolConflictError:
        return "conflict"
    return "committed"


def _scalar(query: str, params: tuple[object, ...]) -> object:
    with _connect() as connection:
        row = connection.execute(query, params).fetchone()
    if row is None:
        raise AssertionError(f"query returned no row: {query}")
    return row[0]


def _assert_identical_redelivery_is_idempotent(prefix: str) -> None:
    object_id = f"{prefix}-same-object"
    process_id = f"{prefix}-same-process"
    protocol_id = protocol_identity(process_id, 1)
    payload = _payload(process_id=process_id, object_id=object_id, version=1)
    _prepare(process_id, object_id)

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _finalize,
                process_id=process_id,
                object_id=object_id,
                version=1,
                barrier=barrier,
            )
            for _ in range(2)
        ]
    outcomes = [future.result(timeout=30) for future in futures]
    if outcomes != ["committed", "committed"]:
        raise AssertionError(f"identical redelivery was not idempotent: {outcomes}")

    protocol_count = _scalar(
        "SELECT count(*) FROM protocols WHERE id = %s", (protocol_id,)
    )
    outbox_count = _scalar(
        "SELECT count(*) FROM integration_outbox WHERE protocol_id = %s", (protocol_id,)
    )
    stored_hash = _scalar(
        "SELECT payload_sha256 FROM protocols WHERE id = %s", (protocol_id,)
    )
    if protocol_count != 1 or outbox_count != 1:
        raise AssertionError(
            f"idempotent finalize produced protocols={protocol_count}, outbox={outbox_count}"
        )
    if stored_hash != protocol_payload_sha256(payload):
        raise AssertionError("stored protocol hash differs from canonical payload")


def _assert_object_version_race_fails_closed(prefix: str) -> None:
    object_id = f"{prefix}-race-object"
    process_ids = (f"{prefix}-race-a", f"{prefix}-race-b")
    for process_id in process_ids:
        _prepare(process_id, object_id)

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _finalize,
                process_id=process_id,
                object_id=object_id,
                version=1,
                barrier=barrier,
            )
            for process_id in process_ids
        ]
    outcomes = sorted(future.result(timeout=30) for future in futures)
    if outcomes != ["committed", "conflict"]:
        raise AssertionError(f"object/version race did not fail closed: {outcomes}")

    protocol_count = _scalar(
        "SELECT count(*) FROM protocols WHERE object_id = %s AND version = 1",
        (object_id,),
    )
    outbox_count = _scalar(
        """SELECT count(*) FROM integration_outbox o
           JOIN protocols p ON p.id = o.protocol_id
          WHERE p.object_id = %s AND p.version = 1""",
        (object_id,),
    )
    finalized_count = _scalar(
        """SELECT count(*) FROM processes
          WHERE object_id = %s AND process_state = 'FINALIZED'""",
        (object_id,),
    )
    if (protocol_count, outbox_count, finalized_count) != (1, 1, 1):
        raise AssertionError(
            "race leaked a partial commit: "
            f"protocols={protocol_count}, outbox={outbox_count}, "
            f"finalized={finalized_count}"
        )


def main() -> None:
    prefix = f"ci-race-{uuid4().hex[:12]}"
    _assert_identical_redelivery_is_idempotent(prefix)
    _assert_object_version_race_fails_closed(prefix)
    print("live PostgreSQL protocol concurrency checks passed")


if __name__ == "__main__":
    main()
