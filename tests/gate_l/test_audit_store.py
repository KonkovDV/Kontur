"""Gate L: AuditStore — MemoryAuditStore и PostgresAuditStore.

Выученные уроки:
  - Статусы берём из домена, не хардкодим
  - Автомат не записывает юридические решения (ADR-0001)
  - getAuditLog есть в REQUIRED_ROLES (PR #48 фиксирует отсутствие)
  - mock-connection: проверяем SQL и параметры
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kontur.infrastructure.db.audit_store import (
    AuditEvent,
    MemoryAuditStore,
    PostgresAuditStore,
    INSERT_AUDIT_SQL,
    LOAD_AUDIT_SQL,
)
from kontur.presentation.rbac import REQUIRED_ROLES, roles_for


# ─────────────────────────────────────── helpers ─────────────────────────────────


def _evt(action: str = "reviewFinding", object_id: str = "proc-1") -> AuditEvent:
    return AuditEvent(
        actor_id="insp-7",
        action=action,
        object_id=object_id,
        payload={"finding_id": "f-1"},
    )


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows


class _MockConnection:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []
        self.calls: list[tuple[str, dict]] = []

    def execute(self, sql: str, params: dict) -> _FakeCursor:
        self.calls.append((sql.strip(), params))
        return _FakeCursor(self._rows)


# ─────────────────────────────────────── rbac фикс ──────────────────────────────


def test_get_audit_log_in_required_roles() -> None:
    """Фикс: getAuditLog должен быть в REQUIRED_ROLES, иначе при любом запросе — ValueError."""
    assert "getAuditLog" in REQUIRED_ROLES
    roles = roles_for("getAuditLog")
    assert "INSPECTOR" in {r.value for r in roles}
    assert "ADMIN" in {r.value for r in roles}


# ─────────────────────────────────────── MemoryAuditStore ────────────────────────


def test_memory_append_and_load() -> None:
    store = MemoryAuditStore()
    event_id = store.append(_evt())
    assert isinstance(event_id, str) and event_id
    events = store.load("proc-1")
    assert len(events) == 1
    assert events[0].actor_id == "insp-7"
    assert events[0].event_id == event_id
    assert events[0].timestamp is not None


def test_memory_load_empty() -> None:
    store = MemoryAuditStore()
    assert store.load("proc-999") == []


def test_memory_events_isolated_by_object() -> None:
    store = MemoryAuditStore()
    store.append(_evt(object_id="proc-A"))
    store.append(_evt(object_id="proc-B"))
    assert len(store.load("proc-A")) == 1
    assert len(store.load("proc-B")) == 1


def test_memory_multiple_events_same_object() -> None:
    store = MemoryAuditStore()
    for action in ["reviewFinding", "finalizeProtocol", "unfinalizeProtocol"]:
        store.append(_evt(action=action))
    events = store.load("proc-1")
    assert len(events) == 3
    assert {e.action for e in events} == {
        "reviewFinding", "finalizeProtocol", "unfinalizeProtocol"
    }


# ─────────────────────────────────────── PostgresAuditStore ──────────────────────


def test_postgres_append_calls_insert() -> None:
    conn = _MockConnection()
    store = PostgresAuditStore(conn)
    event_id = store.append(_evt())
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "audit_log" in sql
    assert params["user_id"] == "insp-7"
    assert params["action"] == "reviewFinding"
    assert params["object_id"] == "proc-1"
    assert isinstance(event_id, str) and len(event_id) == 36  # uuid4


def test_postgres_load_returns_events() -> None:
    ts = datetime.now(tz=UTC)
    row = ("evt-1", "insp-7", "reviewFinding", "proc-1", {"finding_id": "f-1"}, ts)
    conn = _MockConnection(rows=[row])
    store = PostgresAuditStore(conn)
    events = store.load("proc-1")
    assert len(events) == 1
    e = events[0]
    assert e.event_id == "evt-1"
    assert e.actor_id == "insp-7"
    assert e.action == "reviewFinding"
    assert e.payload == {"finding_id": "f-1"}


def test_postgres_load_empty() -> None:
    conn = _MockConnection(rows=[])
    store = PostgresAuditStore(conn)
    assert store.load("proc-999") == []


def test_postgres_load_uses_correct_sql() -> None:
    conn = _MockConnection(rows=[])
    store = PostgresAuditStore(conn)
    store.load("proc-X")
    sql, params = conn.calls[0]
    assert "audit_log" in sql
    assert params == {"object_id": "proc-X"}
