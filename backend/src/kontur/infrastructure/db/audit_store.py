"""Журнал правок инспектора (GAP-EDIT, Gate L).

Два уровня реализации:
  - MemoryAuditStore  — in-memory; журнал пуст после рестарта (PR #42)
  - PostgresAuditStore — пишет в таблицу audit_log (schema.sql, Gate L)

ADR-0001: автомат не пишет юридические решения; журнал фиксирует только
действия субъекта-человека (inspector_id ← subject из токена).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Одна запись журнала."""

    actor_id: str        # subject из токена (e.g. "insp-7")
    action: str          # operationId или произвольная метка
    object_id: str | None = None   # process_id или иной ресурс
    payload: dict[str, Any] = field(default_factory=dict)
    # Проставляется хранилищем при записи; None до сохранения.
    event_id: str | None = None
    timestamp: datetime | None = None


class AuditStore(Protocol):
    def append(self, event: AuditEvent) -> str: ...
    def load(self, object_id: str) -> list[AuditEvent]: ...


# ─────────────────────────────────────── MemoryAuditStore ────────────────────────


class MemoryAuditStore:
    """In-memory: журнал пуст после рестарта. Для тестов и dev-стенда."""

    def __init__(self) -> None:
        # (object_id or '_global') → list[AuditEvent]
        self._log: dict[str, list[AuditEvent]] = {}

    def append(self, event: AuditEvent) -> str:
        """Записать событие; вернуть присвоенный event_id."""
        event_id = str(uuid4())
        ts = datetime.now(tz=UTC)
        stored = AuditEvent(
            actor_id=event.actor_id,
            action=event.action,
            object_id=event.object_id,
            payload=event.payload,
            event_id=event_id,
            timestamp=ts,
        )
        key = event.object_id or "_global"
        self._log.setdefault(key, []).append(stored)
        return event_id

    def load(self, object_id: str) -> list[AuditEvent]:
        return list(self._log.get(object_id, []))

    def clear(self) -> None:
        self._log.clear()


# ─────────────────────────────────────── SQL ─────────────────────────────────────

INSERT_AUDIT_SQL = """
INSERT INTO audit_log (
    id, user_id, action, object_id, details, timestamp
) VALUES (
    %(id)s, %(user_id)s, %(action)s, %(object_id)s, %(details)s::jsonb, %(timestamp)s
)
"""

LOAD_AUDIT_SQL = """
SELECT id, user_id, action, object_id, details, timestamp
FROM   audit_log
WHERE  object_id = %(object_id)s
ORDER  BY timestamp, id
"""


# ─────────────────────────────────────── PostgresAuditStore ──────────────────────


class PostgresAuditStore:
    """Пишет в audit_log из schema.sql. psycopg — extra 'store'."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def append(self, event: AuditEvent) -> str:
        event_id = str(uuid4())
        ts = datetime.now(tz=UTC)
        params = {
            "id": event_id,
            "user_id": event.actor_id,
            "action": event.action,
            "object_id": event.object_id,
            "details": json.dumps(event.payload, ensure_ascii=False),
            "timestamp": ts,
        }
        self._connection.execute(INSERT_AUDIT_SQL, params)  # type: ignore[attr-defined]
        return event_id

    def load(self, object_id: str) -> list[AuditEvent]:
        cursor = self._connection.execute(  # type: ignore[attr-defined]
            LOAD_AUDIT_SQL,
            {"object_id": object_id},
        )
        result: list[AuditEvent] = []
        for row in cursor.fetchall():
            payload: dict[str, Any] = {}
            if row[4] is not None:
                raw = row[4]
                payload = raw if isinstance(raw, dict) else json.loads(raw)
            result.append(
                AuditEvent(
                    event_id=str(row[0]),
                    actor_id=str(row[1]),
                    action=str(row[2]),
                    object_id=None if row[3] is None else str(row[3]),
                    payload=payload,
                    timestamp=row[5] if isinstance(row[5], datetime) else None,
                )
            )
        return result
