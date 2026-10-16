"""PostgresProcessStore на коротких соединениях (один вызов — один connect)."""

from __future__ import annotations

import threading
from collections.abc import Sequence

import psycopg  # type: ignore[import-not-found,import-untyped,unused-ignore]

from kontur.domain.models import Finding
from kontur.infrastructure.db.audit_store import AuditEvent
from kontur.infrastructure.db.migrations import apply_migrations_dsn
from kontur.infrastructure.db.process_store import PostgresProcessStore, ProcessSnapshot


class ConnectingPostgresProcessStore:
    """Каждый метод открывает соединение. Для API-процесса без пула в skeleton."""

    def __init__(self, dsn: str) -> None:
        if not dsn.strip():
            raise ValueError("KONTUR_DB_URL пуст")
        self._dsn = dsn
        self._migrated = False
        self._migration_lock = threading.Lock()

    def _connect(self) -> psycopg.Connection:
        """Соединение; первым делом база догоняет schema.sql (migrations.py).

        Лениво, а не в конструкторе: /healthz ядра не зависит от того, поднят ли
        Postgres. Старые строки становятся читаемыми до первого же запроса.
        """

        if not self._migrated:
            with self._migration_lock:
                if not self._migrated:
                    apply_migrations_dsn(self._dsn)
                    self._migrated = True
        return psycopg.connect(self._dsn)

    def _store(self, connection: object) -> PostgresProcessStore:
        return PostgresProcessStore(connection)

    def load(self, process_id: str) -> ProcessSnapshot | None:
        with self._connect() as connection:
            return self._store(connection).load(process_id)

    def list_all_files(self) -> list[tuple[str, str, str]]:
        with self._connect() as connection:
            return self._store(connection).list_all_files()

    def save(self, snapshot: ProcessSnapshot) -> None:
        with self._connect() as connection:
            self._store(connection).save(snapshot)
            connection.commit()

    def save_finding(self, process_id: str, finding: Finding) -> None:
        with self._connect() as connection:
            self._store(connection).save_finding(process_id, finding)
            connection.commit()

    def load_findings(self, process_id: str) -> list[Finding]:
        with self._connect() as connection:
            return self._store(connection).load_findings(process_id)

    def replace_findings(self, process_id: str, findings: Sequence[Finding]) -> None:
        with self._connect() as connection:
            self._store(connection).replace_findings(process_id, findings)
            connection.commit()

    def save_audit_event(
        self,
        process_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, object],
        *,
        object_id: str | None = None,
    ) -> None:
        with self._connect() as connection:
            self._store(connection).save_audit_event(
                process_id, actor_id, action, payload, object_id=object_id
            )
            connection.commit()

    def load_audit(self, process_id: str) -> list[AuditEvent]:
        with self._connect() as connection:
            return self._store(connection).load_audit(process_id)

    def next_protocol_version(self, object_id: str) -> int:
        with self._connect() as connection:
            return self._store(connection).next_protocol_version(object_id)

    def materialize_finalized(
        self, snapshot: ProcessSnapshot, payload: dict[str, object]
    ) -> None:
        with self._connect() as connection:
            self._store(connection).materialize_finalized(snapshot, payload)
            connection.commit()

    def load_protocol(self, protocol_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            return self._store(connection).load_protocol(protocol_id)

    def load_protocol_version(
        self, object_id: str, version: int
    ) -> dict[str, object] | None:
        with self._connect() as connection:
            return self._store(connection).load_protocol_version(object_id, version)

    def load_full_protocol(self, protocol_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            return self._store(connection).load_full_protocol(protocol_id)

    def load_full_protocol_version(
        self, object_id: str, version: int
    ) -> dict[str, object] | None:
        with self._connect() as connection:
            return self._store(connection).load_full_protocol_version(object_id, version)
