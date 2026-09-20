"""Outbox relay: retries 1/5/15 min, stable event_id, not Rin delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kontur.domain.statuses import ProcessState, Scenario
from kontur.infrastructure.db.process_store import (
    MemoryProcessStore,
    ProcessSnapshot,
    outbox_event_id,
    protocol_payload_sha256,
)
from kontur.infrastructure.outbox import (
    CLAIM_OUTBOX_SQL,
    MAX_ATTEMPTS,
    RETRY_SECONDS,
    RecordingPublisher,
    relay_once_memory,
    retry_delay,
)


def _snap() -> ProcessSnapshot:
    return ProcessSnapshot(
        process_id="p-1",
        object_id="obj-1",
        process_state=ProcessState.FINALIZED,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        finalized_by="insp-7",
        protocol_id="protocol-p-1",
    )


def _payload() -> dict[str, object]:
    return {
        "protocol_id": "protocol-p-1",
        "object_id": "obj-1",
        "version": 1,
        "status": "PROTOCOL_FINALIZED",
        "scenario": "SINGLE_ONLY",
        "upload_status": {"pd": "PD_UPLOADED", "rd": "RD_MISSING", "id": "ID_MISSING"},
        "sections": {
            "completeness": [],
            "candidates": [],
            "confirmed": [],
            "negative_verified": [],
            "suspicions": [],
        },
        "violation_count": 0,
        "versions": {"matrix_version": "draft-0", "model_version": "none"},
        "input_manifest": {"manifest_hash": "pending", "files": []},
    }


def _materialized(available_at: datetime) -> MemoryProcessStore:
    store = MemoryProcessStore()
    store.materialize_finalized(_snap(), _payload())
    store._outbox["protocol-p-1"]["available_at"] = available_at
    return store


def test_retry_schedule_is_one_five_fifteen_minutes() -> None:
    assert RETRY_SECONDS == (60, 300, 900)
    assert retry_delay(1) == timedelta(seconds=60)
    assert retry_delay(2) == timedelta(seconds=300)
    assert retry_delay(3) == timedelta(seconds=900)
    assert retry_delay(MAX_ATTEMPTS) is None


def test_relay_delivers_once_and_keeps_event_id() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    store = _materialized(now)
    publisher = RecordingPublisher()
    assert relay_once_memory(store, publisher, now) == "DELIVERED"
    assert relay_once_memory(store, publisher, now) is None
    event_id = outbox_event_id("protocol-p-1")
    assert len(publisher.events) == 1
    assert publisher.events[0][0] == event_id
    assert store._outbox["protocol-p-1"]["status"] == "DELIVERED"
    digest = protocol_payload_sha256(_payload())
    assert store._outbox["protocol-p-1"]["payload_sha256"] == digest
    assert store._outbox["protocol-p-1"]["event_id"] == event_id


def test_nack_reschedules_one_then_five_then_fifteen_then_terminal() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    store = _materialized(now)
    event_id = outbox_event_id("protocol-p-1")
    delays = (60, 300, 900)
    for index, delay in enumerate(delays):
        publisher = RecordingPublisher(fail_remaining=1)
        assert relay_once_memory(store, publisher, now) == "PENDING"
        item = store._outbox["protocol-p-1"]
        assert item["status"] == "PENDING"
        assert item["event_id"] == event_id
        assert item["attempts"] == index + 1
        assert item["available_at"] == now + timedelta(seconds=delay)
        now = item["available_at"]
        assert isinstance(now, datetime)
    publisher = RecordingPublisher(fail_remaining=1)
    assert relay_once_memory(store, publisher, now) == "FAILED_TERMINAL"
    assert store._outbox["protocol-p-1"]["status"] == "FAILED_TERMINAL"
    assert store._outbox["protocol-p-1"]["attempts"] == 4
    assert publisher.events == []


def test_same_event_id_after_retry_then_confirm() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    store = _materialized(now)
    assert relay_once_memory(store, RecordingPublisher(fail_remaining=1), now) == "PENDING"
    later = now + timedelta(seconds=60)
    publisher = RecordingPublisher()
    assert relay_once_memory(store, publisher, later) == "DELIVERED"
    assert publisher.events[0][0] == outbox_event_id("protocol-p-1")


def test_hash_mismatch_is_terminal() -> None:
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    store = _materialized(now)
    store._outbox["protocol-p-1"]["payload_sha256"] = "a" * 64
    assert relay_once_memory(store, RecordingPublisher(), now) == "FAILED_TERMINAL"
    assert store._outbox["protocol-p-1"]["status"] == "FAILED_TERMINAL"


def test_claim_sql_uses_skip_locked() -> None:
    assert "FOR UPDATE SKIP LOCKED" in CLAIM_OUTBOX_SQL
    assert "attempts < 4" in CLAIM_OUTBOX_SQL
    assert "protocol_id = %(protocol_id)s" in CLAIM_OUTBOX_SQL
