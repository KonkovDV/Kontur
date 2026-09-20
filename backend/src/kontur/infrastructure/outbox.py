"""Outbox relay: PostgreSQL → broker confirm. Not Rin delivery.

At-least-once to the broker. Exactly-once effect needs a consumer inbox.
Retry delays are 1 / 5 / 15 minutes, then FAILED_TERMINAL.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from kontur.infrastructure.db.process_store import (
    MemoryProcessStore,
    _canonical_json,
    _protocol_cell,
    protocol_payload_sha256,
)

RETRY_SECONDS = (60, 300, 900)
LEASE_SECONDS = 30
MAX_ATTEMPTS = 4
ROUTING_KEY = "kontur.rin.protocol"

CLAIM_OUTBOX_SQL = """
WITH picked AS (
    SELECT id
      FROM integration_outbox
     WHERE status IN ('PENDING', 'DELIVERING')
       AND available_at <= %(now)s
       AND attempts < 4
     ORDER BY created_at
     FOR UPDATE SKIP LOCKED
     LIMIT 1
)
UPDATE integration_outbox AS o
   SET status = 'DELIVERING',
       attempts = o.attempts + 1,
       available_at = %(lease_until)s
  FROM picked
 WHERE o.id = picked.id
RETURNING o.id, o.process_id, o.protocol_id, o.event_id, o.payload_sha256, o.attempts
"""

CLAIM_ONE_OUTBOX_SQL = """
WITH picked AS (
    SELECT id
      FROM integration_outbox
     WHERE protocol_id = %(protocol_id)s
       AND status IN ('PENDING', 'DELIVERING')
       AND available_at <= %(now)s
       AND attempts < 4
     ORDER BY created_at
     FOR UPDATE SKIP LOCKED
     LIMIT 1
)
UPDATE integration_outbox AS o
   SET status = 'DELIVERING',
       attempts = o.attempts + 1,
       available_at = %(lease_until)s
  FROM picked
 WHERE o.id = picked.id
RETURNING o.id, o.process_id, o.protocol_id, o.event_id, o.payload_sha256, o.attempts
"""

MARK_DELIVERED_SQL = """
UPDATE integration_outbox
   SET status = 'DELIVERED', last_error = NULL
 WHERE id = %(id)s AND status = 'DELIVERING'
"""

MARK_RETRY_SQL = """
UPDATE integration_outbox
   SET status = 'PENDING',
       available_at = %(available_at)s,
       last_error = %(last_error)s
 WHERE id = %(id)s AND status = 'DELIVERING'
"""

MARK_TERMINAL_SQL = """
UPDATE integration_outbox
   SET status = 'FAILED_TERMINAL',
       last_error = %(last_error)s
 WHERE id = %(id)s AND status = 'DELIVERING'
"""

SELECT_PROTOCOL_PAYLOAD_SQL = """
SELECT payload FROM protocols WHERE id = %(protocol_id)s
"""


class PublishError(RuntimeError):
    """Broker nack, timeout, or missing confirm. Not a Rin rejection."""


class OutboxPublisher(Protocol):
    def publish_confirmed(
        self,
        *,
        event_id: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> None: ...


@dataclass(frozen=True)
class OutboxRow:
    id: str
    process_id: str
    protocol_id: str
    event_id: str
    payload_sha256: str
    attempts: int


@dataclass
class RecordingPublisher:
    """Test double. Confirm is in-process, not AMQP."""

    events: list[tuple[str, bytes]] = field(default_factory=list)
    fail_remaining: int = 0

    def publish_confirmed(
        self,
        *,
        event_id: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> None:
        del headers
        if self.fail_remaining > 0:
            self.fail_remaining -= 1
            raise PublishError("publisher nack")
        self.events.append((event_id, body))


def retry_delay(attempts: int) -> timedelta | None:
    """`attempts` is the count after the failed try (1..4)."""

    if attempts < 1:
        raise ValueError("attempts")
    if attempts >= MAX_ATTEMPTS:
        return None
    return timedelta(seconds=RETRY_SECONDS[attempts - 1])


def _lease_until(now: datetime) -> datetime:
    return now + timedelta(seconds=LEASE_SECONDS)


def _row_from_mapping(item: Mapping[str, object]) -> OutboxRow:
    attempts = item["attempts"]
    if not isinstance(attempts, int) or isinstance(attempts, bool):
        raise TypeError("attempts")
    return OutboxRow(
        id=str(item["id"]),
        process_id=str(item["process_id"]),
        protocol_id=str(item["protocol_id"]),
        event_id=str(item["event_id"]),
        payload_sha256=str(item["payload_sha256"]).strip(),
        attempts=attempts,
    )


def claim_memory(store: MemoryProcessStore, now: datetime) -> OutboxRow | None:
    eligible: list[tuple[datetime, str, dict[str, object]]] = []
    for protocol_id, item in store._outbox.items():
        status = str(item["status"])
        available = item["available_at"]
        attempts = item["attempts"]
        if status not in {"PENDING", "DELIVERING"}:
            continue
        if not isinstance(available, datetime):
            raise TypeError("available_at")
        if not isinstance(attempts, int) or isinstance(attempts, bool):
            raise TypeError("attempts")
        if available > now or attempts >= MAX_ATTEMPTS:
            continue
        eligible.append((available, protocol_id, item))
    if not eligible:
        return None
    eligible.sort(key=lambda pair: (pair[0], pair[1]))
    item = eligible[0][2]
    attempts_value = item["attempts"]
    if not isinstance(attempts_value, int) or isinstance(attempts_value, bool):
        raise TypeError("attempts")
    item["status"] = "DELIVERING"
    item["attempts"] = attempts_value + 1
    item["available_at"] = _lease_until(now)
    return _row_from_mapping(item)


def mark_memory_delivered(store: MemoryProcessStore, outbox_id: str) -> None:
    for item in store._outbox.values():
        if item["id"] == outbox_id and item["status"] == "DELIVERING":
            item["status"] = "DELIVERED"
            item["last_error"] = None
            return
    raise LookupError(outbox_id)


def mark_memory_failed(
    store: MemoryProcessStore,
    row: OutboxRow,
    now: datetime,
    error: str,
    *,
    terminal: bool = False,
) -> str:
    delay = None if terminal else retry_delay(row.attempts)
    for item in store._outbox.values():
        if item["id"] != row.id or item["status"] != "DELIVERING":
            continue
        item["last_error"] = error
        if delay is None:
            item["status"] = "FAILED_TERMINAL"
            return "FAILED_TERMINAL"
        item["status"] = "PENDING"
        item["available_at"] = now + delay
        return "PENDING"
    raise LookupError(row.id)


def memory_protocol_body(store: MemoryProcessStore, protocol_id: str) -> bytes:
    payload = store.load_protocol(protocol_id)
    if payload is None:
        raise LookupError(protocol_id)
    return _canonical_json(payload).encode("utf-8")


def relay_once_memory(
    store: MemoryProcessStore,
    publisher: OutboxPublisher,
    now: datetime | None = None,
) -> str | None:
    moment = now or datetime.now(tz=UTC)
    row = claim_memory(store, moment)
    if row is None:
        return None

    def _fail(error: str, terminal: bool = False) -> str:
        return mark_memory_failed(store, row, moment, error, terminal=terminal)

    return _publish_row(
        row,
        body=memory_protocol_body(store, row.protocol_id),
        publisher=publisher,
        mark_delivered=lambda: mark_memory_delivered(store, row.id),
        mark_failed=_fail,
    )


def claim_postgres(connection: object, now: datetime) -> OutboxRow | None:
    cursor = connection.execute(  # type: ignore[attr-defined]
        CLAIM_OUTBOX_SQL, {"now": now, "lease_until": _lease_until(now)}
    )
    fetched = cursor.fetchone()
    if fetched is None:
        return None
    return OutboxRow(
        id=str(fetched[0]),
        process_id=str(fetched[1]),
        protocol_id=str(fetched[2]),
        event_id=str(fetched[3]),
        payload_sha256=str(fetched[4]).strip(),
        attempts=int(fetched[5]),
    )


def postgres_protocol_body(connection: object, protocol_id: str) -> bytes:
    cursor = connection.execute(  # type: ignore[attr-defined]
        SELECT_PROTOCOL_PAYLOAD_SQL, {"protocol_id": protocol_id}
    )
    fetched = cursor.fetchone()
    if fetched is None:
        raise LookupError(protocol_id)
    payload = _protocol_cell(fetched[0])
    return _canonical_json(payload).encode("utf-8")


def mark_postgres_delivered(connection: object, outbox_id: str) -> None:
    connection.execute(MARK_DELIVERED_SQL, {"id": outbox_id})  # type: ignore[attr-defined]


def mark_postgres_failed(
    connection: object,
    row: OutboxRow,
    now: datetime,
    error: str,
    *,
    terminal: bool = False,
) -> str:
    delay = None if terminal else retry_delay(row.attempts)
    if delay is None:
        connection.execute(  # type: ignore[attr-defined]
            MARK_TERMINAL_SQL, {"id": row.id, "last_error": error}
        )
        return "FAILED_TERMINAL"
    connection.execute(  # type: ignore[attr-defined]
        MARK_RETRY_SQL,
        {"id": row.id, "available_at": now + delay, "last_error": error},
    )
    return "PENDING"


def relay_once_postgres(
    connection: object,
    publisher: OutboxPublisher,
    now: datetime | None = None,
) -> str | None:
    moment = now or datetime.now(tz=UTC)
    row = claim_postgres(connection, moment)
    if row is None:
        return None

    def _fail(error: str, terminal: bool = False) -> str:
        return mark_postgres_failed(
            connection, row, moment, error, terminal=terminal
        )

    return _publish_row(
        row,
        body=postgres_protocol_body(connection, row.protocol_id),
        publisher=publisher,
        mark_delivered=lambda: mark_postgres_delivered(connection, row.id),
        mark_failed=_fail,
    )


def _publish_row(
    row: OutboxRow,
    *,
    body: bytes,
    publisher: OutboxPublisher,
    mark_delivered: Callable[[], None],
    mark_failed: Callable[..., str],
) -> str:
    digest = protocol_payload_sha256(_protocol_cell(body.decode("utf-8")))
    if digest != row.payload_sha256:
        return mark_failed("payload_sha256 mismatch", terminal=True)
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
        return mark_failed(str(exc))
    mark_delivered()
    return "DELIVERED"
