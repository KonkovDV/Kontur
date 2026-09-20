"""Transactional inbox: exactly-once effect for at-least-once redelivery.

ACK the broker only after the PostgreSQL transaction commits. A publisher
confirm or an inbox RECEIVED row is not a Rin business acknowledgement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from kontur.infrastructure.db.process_store import (
    _protocol_cell,
    protocol_payload_sha256,
)
from kontur.infrastructure.outbox import MAX_ATTEMPTS

INSERT_INBOX_SQL = """
INSERT INTO integration_inbox (
    event_id, process_id, protocol_id, payload_sha256,
    status, delivery_attempts, last_error
) VALUES (
    %(event_id)s, %(process_id)s, %(protocol_id)s, %(payload_sha256)s,
    %(status)s, %(delivery_attempts)s, %(last_error)s
)
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id
"""


class InboxChannel(Protocol):
    def ack(self, delivery_tag: str) -> None: ...

    def nack(self, delivery_tag: str, *, requeue: bool) -> None: ...


@dataclass(frozen=True, slots=True)
class BrokerDelivery:
    event_id: str
    process_id: str
    protocol_id: str
    payload_sha256: str
    body: bytes
    redelivery_count: int = 1
    delivery_tag: str = "1"


@dataclass(frozen=True, slots=True)
class InboxRow:
    event_id: str
    process_id: str
    protocol_id: str
    payload_sha256: str
    status: str
    delivery_attempts: int
    last_error: str | None = None


class RecordingInboxChannel:
    """Test double. Settlement order is the contract under test."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, bool | None]] = []

    def ack(self, delivery_tag: str) -> None:
        self.calls.append(("ack", delivery_tag, None))

    def nack(self, delivery_tag: str, *, requeue: bool) -> None:
        self.calls.append(("nack", delivery_tag, requeue))


def payload_digest(body: bytes) -> str:
    return protocol_payload_sha256(_protocol_cell(body.decode("utf-8")))


def classify_inbox_delivery(delivery: BrokerDelivery) -> tuple[str, InboxRow | None]:
    """Return ack | requeue | dead_letter and the row to persist, if any."""

    if delivery.redelivery_count < 1:
        raise ValueError("redelivery_count must be positive")
    error = _delivery_error(delivery)
    attempts = min(delivery.redelivery_count, MAX_ATTEMPTS)
    if error is None:
        return (
            "ack",
            InboxRow(
                event_id=delivery.event_id,
                process_id=delivery.process_id,
                protocol_id=delivery.protocol_id,
                payload_sha256=delivery.payload_sha256,
                status="RECEIVED",
                delivery_attempts=attempts,
            ),
        )
    if delivery.redelivery_count < MAX_ATTEMPTS:
        return "requeue", None
    if not (
        delivery.event_id.strip()
        and delivery.process_id.strip()
        and delivery.protocol_id.strip()
    ):
        return "dead_letter", None
    return (
        "dead_letter",
        InboxRow(
            event_id=delivery.event_id,
            process_id=delivery.process_id,
            protocol_id=delivery.protocol_id,
            payload_sha256=_usable_sha(delivery.payload_sha256),
            status="POISON",
            delivery_attempts=MAX_ATTEMPTS,
            last_error=error,
        ),
    )


def insert_inbox(connection: object, row: InboxRow) -> bool:
    cursor = connection.execute(  # type: ignore[attr-defined]
        INSERT_INBOX_SQL,
        {
            "event_id": row.event_id,
            "process_id": row.process_id,
            "protocol_id": row.protocol_id,
            "payload_sha256": row.payload_sha256,
            "status": row.status,
            "delivery_attempts": row.delivery_attempts,
            "last_error": row.last_error,
        },
    )
    fetched = cursor.fetchone()
    return fetched is not None


def settle_inbox_delivery(
    connection: object,
    delivery: BrokerDelivery,
    channel: InboxChannel,
) -> str:
    """Persist then commit, then ACK. Does not close process synchronization."""

    action, row = classify_inbox_delivery(delivery)
    first = False
    try:
        if row is not None:
            first = insert_inbox(connection, row)
        if action == "requeue":
            connection.rollback()  # type: ignore[attr-defined]
            channel.nack(delivery.delivery_tag, requeue=True)
            return "NACK_REQUEUE"
        if action == "dead_letter" and row is None:
            connection.rollback()  # type: ignore[attr-defined]
            channel.nack(delivery.delivery_tag, requeue=False)
            return "NACK_DEAD_LETTER"
        connection.commit()  # type: ignore[attr-defined]
    except Exception:
        connection.rollback()  # type: ignore[attr-defined]
        raise
    if action == "dead_letter" and first:
        channel.nack(delivery.delivery_tag, requeue=False)
        return "NACK_DEAD_LETTER"
    channel.ack(delivery.delivery_tag)
    return "ACK"


def _delivery_error(delivery: BrokerDelivery) -> str | None:
    if not delivery.event_id.strip():
        return "missing event_id"
    if not delivery.process_id.strip() or not delivery.protocol_id.strip():
        return "missing process/protocol"
    try:
        digest = payload_digest(delivery.body)
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
        return "invalid protocol payload"
    if digest != delivery.payload_sha256.strip().lower():
        return "payload_sha256 mismatch"
    return None


def _usable_sha(value: str) -> str:
    candidate = value.strip().lower()
    if len(candidate) == 64 and all(char in "0123456789abcdef" for char in candidate):
        return candidate
    return "0" * 64


def header_str(headers: Mapping[str, object], name: str) -> str:
    raw = headers.get(name, "")
    return "" if raw is None else str(raw)
