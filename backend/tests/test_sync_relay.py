"""Process sync state follows broker delivery without claiming a Rin ACK."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kontur.infrastructure.outbox import OutboxRow
from kontur.infrastructure.sync_relay import (
    INSERT_SYNC_AUDIT_SQL,
    RESET_FAILED_OUTBOX_SQL,
    UPDATE_PROCESS_SYNC_SQL,
    SyncLifecycleError,
    record_sync_claimed,
    record_sync_outcome,
    retry_failed_sync,
)


class _Cursor:
    def __init__(self, row: object | None = None) -> None:
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class _Connection:
    def __init__(self, *, process_exists: bool = True) -> None:
        self.process_exists = process_exists
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.failed_row: tuple[str, str, str] | None = (
            "outbox-protocol-p-1",
            "protocol-p-1",
            "rin-protocol-p-1",
        )

    def execute(self, sql: str, params: dict[str, object]) -> _Cursor:
        self.calls.append((sql, params))
        if sql == UPDATE_PROCESS_SYNC_SQL:
            return _Cursor((params["process_id"],) if self.process_exists else None)
        if sql == RESET_FAILED_OUTBOX_SQL:
            return _Cursor(self.failed_row)
        return _Cursor()


def _row(attempts: int = 1) -> OutboxRow:
    return OutboxRow(
        id="outbox-protocol-p-1",
        process_id="p-1",
        protocol_id="protocol-p-1",
        event_id="rin-protocol-p-1",
        payload_sha256="a" * 64,
        attempts=attempts,
    )


def _process_updates(connection: _Connection) -> list[dict[str, object]]:
    return [params for sql, params in connection.calls if sql == UPDATE_PROCESS_SYNC_SQL]


def test_claim_moves_process_to_syncing_without_claiming_rin_ack() -> None:
    connection = _Connection()
    record_sync_claimed(connection, _row(2))
    assert _process_updates(connection) == [
        {
            "process_id": "p-1",
            "protocol_id": "protocol-p-1",
            "sync_state": "SYNCING",
            "attempts": 2,
            "last_error": None,
        }
    ]


def test_broker_confirm_stays_syncing_and_retry_wait_is_separate() -> None:
    delivered = _Connection()
    record_sync_outcome(delivered, _row(1), "DELIVERED")
    assert _process_updates(delivered)[0]["sync_state"] == "SYNCING"

    pending = _Connection()
    record_sync_outcome(pending, _row(2), "PENDING", error="publisher nack")
    update = _process_updates(pending)[0]
    assert update["sync_state"] == "RETRY_WAIT"
    assert update["last_error"] == "publisher nack"


def test_exhaustion_returns_to_manual_pending_and_is_audited() -> None:
    connection = _Connection()
    record_sync_outcome(connection, _row(4), "FAILED_TERMINAL", error="timeout")
    update = _process_updates(connection)[0]
    assert update["sync_state"] == "PENDING_SYNC"
    assert update["attempts"] == 4
    audit = [params for sql, params in connection.calls if sql == INSERT_SYNC_AUDIT_SQL]
    assert len(audit) == 1
    assert audit[0]["action"] == "SYNC_RETRY_EXHAUSTED"
    assert "requires_manual_retry" in str(audit[0]["details"])


def test_missing_finalized_process_fails_closed() -> None:
    with pytest.raises(SyncLifecycleError, match="process/protocol"):
        record_sync_claimed(_Connection(process_exists=False), _row())


def test_manual_retry_resets_attempts_and_records_actor() -> None:
    connection = _Connection()
    stamp = datetime(2026, 9, 20, 19, 0, tzinfo=UTC)
    assert retry_failed_sync(connection, "p-1", "admin-7", stamp) == "outbox-protocol-p-1"
    update = _process_updates(connection)[0]
    assert update["sync_state"] == "PENDING_SYNC"
    assert update["attempts"] == 0
    audit = [params for sql, params in connection.calls if sql == INSERT_SYNC_AUDIT_SQL]
    assert audit[0]["user_id"] == "admin-7"
    assert audit[0]["action"] == "SYNC_MANUAL_RETRY"


def test_manual_retry_requires_human_actor_and_failed_row() -> None:
    connection = _Connection()
    with pytest.raises(ValueError, match="actor_id"):
        retry_failed_sync(connection, "p-1", "  ")
    connection.failed_row = None
    with pytest.raises(LookupError, match="no failed outbox"):
        retry_failed_sync(connection, "p-1", "admin-7")
