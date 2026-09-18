"""Журнал действий процесса: таблица `audit_log` (ТЗ п. 12, GAP-EDIT)."""

from __future__ import annotations

import json
from uuid import uuid4

INSERT_AUDIT_SQL = """
INSERT INTO audit_log (id, user_id, action, object_id, process_id, details)
VALUES (
    %(id)s, %(user_id)s, %(action)s, %(object_id)s, %(process_id)s, %(details)s::jsonb
)
"""

SELECT_AUDIT_SQL = """
SELECT user_id, action, details
FROM audit_log
WHERE process_id = %(process_id)s
ORDER BY timestamp, id
"""

AuditEvent = tuple[str, str, dict[str, object]]


def _details(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, str):
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return {str(key): value for key, value in loaded.items()}
    raise TypeError("audit details")


class PostgresAuditStore:
    """Пишет в schema.sql `audit_log`. psycopg — extra `store`."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def save_event(
        self,
        process_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, object],
        *,
        object_id: str | None = None,
    ) -> None:
        self._connection.execute(  # type: ignore[attr-defined]
            INSERT_AUDIT_SQL,
            {
                "id": str(uuid4()),
                "user_id": actor_id,
                "action": action,
                "object_id": object_id,
                "process_id": process_id,
                "details": json.dumps(payload, ensure_ascii=False),
            },
        )

    def load_events(self, process_id: str) -> list[AuditEvent]:
        cursor = self._connection.execute(  # type: ignore[attr-defined]
            SELECT_AUDIT_SQL, {"process_id": process_id}
        )
        events: list[AuditEvent] = []
        for row in cursor.fetchall():
            events.append((str(row[0]), str(row[1]), _details(row[2])))
        return events
