"""Live PostgreSQL proof for transactional inbox settlement.

ACK is issued only after commit. Duplicate event_id is an exactly-once effect,
not exactly-once transport. Inbox RECEIVED does not mark the process synced.
"""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg

from kontur.application.protocol import protocol_identity
from kontur.domain.statuses import ProcessState, Scenario
from kontur.infrastructure.db.process_store import (
    PostgresProcessStore,
    ProcessSnapshot,
    _canonical_json,
    protocol_payload_sha256,
)
from kontur.infrastructure.inbox import (
    BrokerDelivery,
    RecordingInboxChannel,
    settle_inbox_delivery,
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
            "dataset_version": "inbox-live-v1",
        },
        "input_manifest": {"manifest_hash": "inbox-live", "files": []},
    }


def _setup(process_id: str, object_id: str) -> tuple[str, bytes, str]:
    protocol_id = protocol_identity(process_id, 1)
    payload = _payload(process_id, object_id)
    body = _canonical_json(payload).encode("utf-8")
    digest = protocol_payload_sha256(payload)
    base = ProcessSnapshot(
        process_id=process_id,
        object_id=object_id,
        process_state=ProcessState.COMPLETED,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        dataset_version="inbox-live-v1",
        input_manifest_hash="inbox-live",
    )
    final = ProcessSnapshot(
        process_id=process_id,
        object_id=object_id,
        process_state=ProcessState.FINALIZED,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        dataset_version="inbox-live-v1",
        input_manifest_hash="inbox-live",
        finalized_by="inspector-live",
        protocol_id=protocol_id,
    )
    with psycopg.connect(DSN, autocommit=True) as connection:
        store = PostgresProcessStore(connection)
        store.save(base)
        store.materialize_finalized(final, payload)
    return protocol_id, body, digest


def _counts(process_id: str) -> tuple[int, str | None, str]:
    with psycopg.connect(DSN, autocommit=True) as connection:
        inbox = connection.execute(
            """SELECT count(*), max(status)
                 FROM integration_inbox
                WHERE process_id = %s""",
            (process_id,),
        ).fetchone()
        sync = connection.execute(
            "SELECT sync_state FROM processes WHERE id = %s",
            (process_id,),
        ).fetchone()
    if inbox is None or sync is None:
        raise AssertionError("inbox/process row missing")
    status = None if inbox[1] is None else str(inbox[1])
    return int(inbox[0]), status, str(sync[0])


def main() -> None:
    suffix = uuid4().hex[:12]
    process_id = f"inbox-live-{suffix}"
    object_id = f"inbox-object-{suffix}"
    protocol_id, body, digest = _setup(process_id, object_id)
    event_id = f"rin-{protocol_id}"
    delivery = BrokerDelivery(
        event_id=event_id,
        process_id=process_id,
        protocol_id=protocol_id,
        payload_sha256=digest,
        body=body,
        redelivery_count=1,
        delivery_tag="live-1",
    )

    with psycopg.connect(DSN) as crashed:
        crashed.execute(
            """INSERT INTO integration_inbox (
                   event_id, process_id, protocol_id, payload_sha256, status
               ) VALUES (%s, %s, %s, %s, 'RECEIVED')""",
            (event_id, process_id, protocol_id, digest),
        )
        crashed.rollback()
    if _counts(process_id)[0] != 0:
        raise AssertionError("rollback leaked an inbox row")

    with psycopg.connect(DSN) as connection:
        channel = RecordingInboxChannel()
        result = settle_inbox_delivery(connection, delivery, channel)
    if result != "ACK" or channel.calls != [("ack", "live-1", None)]:
        raise AssertionError(f"first settle failed: {result} {channel.calls}")
    count, status, sync_state = _counts(process_id)
    if count != 1 or status != "RECEIVED":
        raise AssertionError(f"expected one RECEIVED row, got {count} {status}")
    if sync_state in {"SYNCED", "FAILED_TERMINAL"}:
        raise AssertionError(f"inbox must not close sync, got {sync_state}")

    with psycopg.connect(DSN) as connection:
        channel = RecordingInboxChannel()
        result = settle_inbox_delivery(connection, delivery, channel)
    if result != "ACK":
        raise AssertionError(f"duplicate settle failed: {result}")
    if _counts(process_id)[0] != 1:
        raise AssertionError("duplicate event_id inserted a second row")

    poison = BrokerDelivery(
        event_id=f"rin-{protocol_id}-bad",
        process_id=process_id,
        protocol_id=protocol_id,
        payload_sha256="b" * 64,
        body=body,
        redelivery_count=4,
        delivery_tag="live-poison",
    )
    with psycopg.connect(DSN) as connection:
        channel = RecordingInboxChannel()
        result = settle_inbox_delivery(connection, poison, channel)
    if result != "NACK_DEAD_LETTER" or channel.calls != [("nack", "live-poison", False)]:
        raise AssertionError(f"poison settle failed: {result} {channel.calls}")
    with psycopg.connect(DSN, autocommit=True) as connection:
        poison_row = connection.execute(
            """SELECT status, last_error FROM integration_inbox
                WHERE event_id = %s""",
            (poison.event_id,),
        ).fetchone()
        still_sync = connection.execute(
            "SELECT sync_state FROM processes WHERE id = %s",
            (process_id,),
        ).fetchone()
    if poison_row is None or str(poison_row[0]) != "POISON":
        raise AssertionError(f"expected POISON row, got {poison_row}")
    if still_sync is None or str(still_sync[0]) in {"SYNCED"}:
        raise AssertionError(f"poison path closed sync: {still_sync}")
    print("live PostgreSQL inbox checks passed")


if __name__ == "__main__":
    main()
