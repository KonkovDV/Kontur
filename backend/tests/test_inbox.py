"""Transactional inbox: ACK after commit, unique event_id, no Rin ACK."""

from __future__ import annotations

from pathlib import Path

import pytest

from kontur.domain.state_machines import TransitionError, advance_sync
from kontur.domain.statuses import SyncState
from kontur.infrastructure.inbox import (
    INSERT_INBOX_SQL,
    BrokerDelivery,
    RecordingInboxChannel,
    classify_inbox_delivery,
    payload_digest,
    settle_inbox_delivery,
)

BODY = b'{"object_id":"o-1","protocol_id":"protocol-p-1","version":1}'
SHA = payload_digest(BODY)
INBOX_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "kontur"
    / "infrastructure"
    / "inbox.py"
).read_text(encoding="utf-8")


class _Cursor:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class _Connection:
    def __init__(self, *, duplicate: bool = False, fail_insert: bool = False) -> None:
        self.duplicate = duplicate
        self.fail_insert = fail_insert
        self.order: list[str] = []
        self.rows: list[dict[str, object]] = []

    def execute(self, sql: str, params: dict[str, object]) -> _Cursor:
        del sql
        self.order.append("insert")
        if self.fail_insert:
            raise RuntimeError("postgresql://user:secret@example.invalid/kontur")
        if self.duplicate:
            return _Cursor(None)
        self.rows.append(params)
        return _Cursor((params["event_id"],))

    def commit(self) -> None:
        self.order.append("commit")

    def rollback(self) -> None:
        self.order.append("rollback")


def _delivery(**overrides: object) -> BrokerDelivery:
    payload = {
        "event_id": "rin-protocol-p-1",
        "process_id": "p-1",
        "protocol_id": "protocol-p-1",
        "payload_sha256": SHA,
        "body": BODY,
        "redelivery_count": 1,
        "delivery_tag": "tag-1",
    }
    payload.update(overrides)
    return BrokerDelivery(
        event_id=str(payload["event_id"]),
        process_id=str(payload["process_id"]),
        protocol_id=str(payload["protocol_id"]),
        payload_sha256=str(payload["payload_sha256"]),
        body=bytes(payload["body"]) if isinstance(payload["body"], bytes) else BODY,
        redelivery_count=int(payload["redelivery_count"]),
        delivery_tag=str(payload["delivery_tag"]),
    )


def test_valid_delivery_inserts_then_commits_then_acks() -> None:
    connection = _Connection()
    channel = RecordingInboxChannel()
    assert settle_inbox_delivery(connection, _delivery(), channel) == "ACK"
    assert connection.order == ["insert", "commit"]
    assert channel.calls == [("ack", "tag-1", None)]
    assert connection.rows[0]["status"] == "RECEIVED"
    assert connection.rows[0]["event_id"] == "rin-protocol-p-1"


def test_duplicate_event_id_is_idempotent_and_still_acks() -> None:
    connection = _Connection(duplicate=True)
    channel = RecordingInboxChannel()
    assert settle_inbox_delivery(connection, _delivery(), channel) == "ACK"
    assert connection.order == ["insert", "commit"]
    assert channel.calls == [("ack", "tag-1", None)]
    assert connection.rows == []


def test_hash_mismatch_requeues_without_ack_before_limit() -> None:
    connection = _Connection()
    channel = RecordingInboxChannel()
    result = settle_inbox_delivery(
        connection,
        _delivery(payload_sha256="b" * 64, redelivery_count=2),
        channel,
    )
    assert result == "NACK_REQUEUE"
    assert connection.order == ["rollback"]
    assert channel.calls == [("nack", "tag-1", True)]
    assert connection.rows == []


def test_fourth_poison_delivery_dead_letters_after_commit() -> None:
    connection = _Connection()
    channel = RecordingInboxChannel()
    result = settle_inbox_delivery(
        connection,
        _delivery(payload_sha256="b" * 64, redelivery_count=4),
        channel,
    )
    assert result == "NACK_DEAD_LETTER"
    assert connection.order == ["insert", "commit"]
    assert channel.calls == [("nack", "tag-1", False)]
    assert connection.rows[0]["status"] == "POISON"
    assert connection.rows[0]["last_error"] == "payload_sha256 mismatch"


def test_insert_failure_rolls_back_and_never_acks() -> None:
    connection = _Connection(fail_insert=True)
    channel = RecordingInboxChannel()
    with pytest.raises(RuntimeError, match="postgresql"):
        settle_inbox_delivery(connection, _delivery(), channel)
    assert connection.order == ["insert", "rollback"]
    assert channel.calls == []


def test_classify_rejects_busy_loop_count() -> None:
    with pytest.raises(ValueError, match="redelivery_count"):
        classify_inbox_delivery(_delivery(redelivery_count=0))


def test_inbox_sql_and_module_never_write_process_sync() -> None:
    assert "ON CONFLICT (event_id) DO NOTHING" in INSERT_INBOX_SQL
    assert "UPDATE processes" not in INBOX_SOURCE
    assert "SET sync_state" not in INBOX_SOURCE


def test_sync_machine_allows_transport_exhaustion_back_to_pending() -> None:
    assert (
        advance_sync(SyncState.SYNCING, SyncState.PENDING_SYNC) is SyncState.PENDING_SYNC
    )
    with pytest.raises(TransitionError):
        advance_sync(SyncState.SYNCED, SyncState.PENDING_SYNC)
    with pytest.raises(TransitionError):
        advance_sync(SyncState.PENDING_SYNC, SyncState.SYNCED)
