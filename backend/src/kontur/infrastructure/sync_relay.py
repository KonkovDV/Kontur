"""Relay lifecycle projected into process sync state.

Broker acceptance is not a Rin acknowledgement. DELIVERED outbox rows therefore
leave the process in SYNCING until a later Rin adapter records a business ACK.
After 1/5/15 minute retries are exhausted, the protocol returns to PENDING_SYNC
for an explicit human retry and an idempotent audit signal is recorded.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from kontur.infrastructure.db.process_store import (
    _protocol_cell,
    protocol_payload_sha256,
)
from kontur.infrastructure.outbox import (
    OutboxPublisher,
    OutboxRow,
    PublishError,
    claim_postgres,
    mark_postgres_delivered,
    mark_postgres_failed,
    postgres_protocol_body,
)

UPDATE_PROCESS_SYNC_SQL = """
UPDATE processes
   SET sync_state = %(sync_state)s,
       sync_attempts = %(attempts)s,
       last_error_code = %(last_error)s,
       updated_at = now()
 WHERE id = %(process_id)s
   AND process_state = 'FINALIZED'
   AND protocol_id = %(protocol_id)s
RETURNING id
"""

INSERT_SYNC_AUDIT_SQL = """
INSERT INTO audit_log (id, user_id, action, object_id, process_id, details)
SELECT %(id)s, %(user_id)s, %(action)s, p.object_id, p.id, %(details)s::jsonb
  FROM processes AS p
 WHERE p.id = %(process_id)s
ON CONFLICT (id) DO NOTHING
"""

RESET_FAILED_OUTBOX_SQL = """
UPDATE integration_outbox
   SET status = 'PENDING',
       attempts = 0,
       available_at = %(now)s,
       last_error = NULL
 WHERE process_id = %(process_id)s
   AND status = 'FAILED_TERMINAL'
RETURNING id, protocol_id, event_id
"""


class SyncLifecycleError(RuntimeError):
    """Outbox/process state could not be changed atomically."""


def _update_process(
    connection: object,
    row: OutboxRow,
    *,
    sync_state: str,
    attempts: int,
    last_error: str | None,
) -> None:
    cursor = connection.execute(  # type: ignore[attr-defined]
        UPDATE_PROCESS_SYNC_SQL,
        {
            "process_id": row.process_id,
            "protocol_id": row.protocol_id,
            "sync_state": sync_state,
            "attempts": attempts,
            "last_error": last_error,
        },
    )
    if cursor.fetchone() is None:
        raise SyncLifecycleError(
            f"finalized process/protocol pair missing for event {row.event_id}"
        )


def _audit(
    connection: object,
    row: OutboxRow,
    *,
    actor_id: str,
    action: str,
    details: dict[str, object],
) -> None:
    connection.execute(  # type: ignore[attr-defined]
        INSERT_SYNC_AUDIT_SQL,
        {
            "id": f"audit-{action.lower()}-{row.event_id}",
            "user_id": actor_id,
            "action": action,
            "process_id": row.process_id,
            "details": json.dumps(details, ensure_ascii=False, sort_keys=True),
        },
    )


def record_sync_claimed(connection: object, row: OutboxRow) -> None:
    _update_process(
        connection,
        row,
        sync_state="SYNCING",
        attempts=row.attempts,
        last_error=None,
    )


def record_sync_outcome(
    connection: object,
    row: OutboxRow,
    outcome: str,
    *,
    error: str | None = None,
) -> None:
    if outcome == "DELIVERED":
        # Publisher confirm is only broker acceptance. Rin has not ACKed yet.
        state = "SYNCING"
        last_error = None
    elif outcome == "PENDING":
        state = "RETRY_WAIT"
        last_error = error
    elif outcome == "FAILED_TERMINAL":
        # Communication failure must not invalidate the inspector's decision.
        state = "PENDING_SYNC"
        last_error = error
    else:
        raise ValueError(f"unknown relay outcome: {outcome}")

    _update_process(
        connection,
        row,
        sync_state=state,
        attempts=row.attempts,
        last_error=last_error,
    )
    if outcome == "FAILED_TERMINAL":
        _audit(
            connection,
            row,
            actor_id="system:outbox-relay",
            action="SYNC_RETRY_EXHAUSTED",
            details={
                "event_id": row.event_id,
                "protocol_id": row.protocol_id,
                "attempts": row.attempts,
                "requires_manual_retry": True,
                "error_code": error,
            },
        )


def relay_once_postgres_with_sync(
    connection: object,
    publisher: OutboxPublisher,
    now: datetime | None = None,
) -> str | None:
    moment = now or datetime.now(tz=UTC)
    row = claim_postgres(connection, moment)
    if row is None:
        return None
    record_sync_claimed(connection, row)

    body = postgres_protocol_body(connection, row.protocol_id)
    digest = protocol_payload_sha256(_protocol_cell(body.decode("utf-8")))
    if digest != row.payload_sha256:
        error = "payload_sha256 mismatch"
        outcome = mark_postgres_failed(
            connection, row, moment, error, terminal=True
        )
        record_sync_outcome(connection, row, outcome, error=error)
        return outcome

    try:
        publisher.publish_confirmed(
            event_id=row.event_id,
            body=body,
            headers={
                "process_id": row.process_id,
                "protocol_id": row.protocol_id,
                "payload_sha256": row.payload_sha256,
            },
        )
    except PublishError as exc:
        error = str(exc)
        outcome = mark_postgres_failed(connection, row, moment, error)
        record_sync_outcome(connection, row, outcome, error=error)
        return outcome

    mark_postgres_delivered(connection, row.id)
    record_sync_outcome(connection, row, "DELIVERED")
    return "DELIVERED"


def retry_failed_sync(
    connection: object,
    process_id: str,
    actor_id: str,
    now: datetime | None = None,
) -> str:
    if not process_id.strip():
        raise ValueError("process_id is required")
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    moment = now or datetime.now(tz=UTC)
    cursor = connection.execute(  # type: ignore[attr-defined]
        RESET_FAILED_OUTBOX_SQL,
        {"process_id": process_id, "now": moment},
    )
    fetched = cursor.fetchone()
    if fetched is None:
        raise LookupError(f"no failed outbox row for process {process_id}")
    row = OutboxRow(
        id=str(fetched[0]),
        process_id=process_id,
        protocol_id=str(fetched[1]),
        event_id=str(fetched[2]),
        payload_sha256="",
        attempts=0,
    )
    _update_process(
        connection,
        row,
        sync_state="PENDING_SYNC",
        attempts=0,
        last_error=None,
    )
    _audit(
        connection,
        row,
        actor_id=actor_id,
        action="SYNC_MANUAL_RETRY",
        details={
            "event_id": row.event_id,
            "protocol_id": row.protocol_id,
            "requested_at": moment.isoformat(),
        },
    )
    return row.id
