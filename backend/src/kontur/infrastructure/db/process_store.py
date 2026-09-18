"""Снимок процесса по таблице `processes` (ТЗ п. 9.1, RT-2609-27).

Находки, файлы и комплектность в этой таблице не живут: после рестарта
восстанавливаются id, состояние, сценарий и выгрузка, не очередь инспектора.
Протокол ТЗ по-прежнему не выдумывается: placeholder нужен только CHECK
`finalized_needs_human` (protocol_id NOT NULL при FINALIZED).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from kontur.domain.models import Finding
from kontur.domain.statuses import ProcessState, Scenario, SyncState

MAX_PARSE_ATTEMPTS = 3
MAX_SYNC_ATTEMPTS = 4


@dataclass(frozen=True, slots=True)
class ProcessSnapshot:
    process_id: str
    object_id: str
    process_state: ProcessState
    scenario: Scenario
    matrix_version: str
    model_version: str
    dataset_version: str | None = None
    parse_attempts: int = 0
    sync_attempts: int = 0
    sync_state: SyncState = SyncState.NOT_REQUESTED
    last_error_code: str | None = None
    finalized_by: str | None = None
    protocol_id: str | None = None


class ProcessStore(Protocol):
    def load(self, process_id: str) -> ProcessSnapshot | None: ...

    def save(self, snapshot: ProcessSnapshot) -> None: ...

    def save_finding(self, process_id: str, finding: Finding) -> None: ...

    def load_findings(self, process_id: str) -> list[Finding]: ...


def validate_snapshot(snapshot: ProcessSnapshot) -> None:
    """Те же границы, что CHECK в schema.sql. Молчание не считается успехом."""

    if not snapshot.process_id.strip() or not snapshot.object_id.strip():
        raise ValueError("process_id и object_id обязательны")
    if not 0 <= snapshot.parse_attempts <= MAX_PARSE_ATTEMPTS:
        raise ValueError("parse_attempts вне 0..3")
    if not 0 <= snapshot.sync_attempts <= MAX_SYNC_ATTEMPTS:
        raise ValueError("sync_attempts вне 0..4")
    if snapshot.process_state is ProcessState.FINALIZED:
        if snapshot.finalized_by is None or not snapshot.finalized_by.strip():
            raise ValueError("FINALIZED требует finalized_by")
        if snapshot.protocol_id is None or not snapshot.protocol_id.strip():
            raise ValueError("FINALIZED требует protocol_id")
    if snapshot.sync_state is not SyncState.NOT_REQUESTED:
        if snapshot.process_state is not ProcessState.FINALIZED:
            raise ValueError("выгрузка только после FINALIZED")
        if snapshot.protocol_id is None or not snapshot.protocol_id.strip():
            raise ValueError("выгрузка без protocol_id запрещена")


class MemoryProcessStore:
    """Исполняемый DAO без Postgres: те же инварианты, что в schema.sql."""

    def __init__(self) -> None:
        self._rows: dict[str, ProcessSnapshot] = {}
        self._findings: dict[str, dict[str, Finding]] = {}

    def load(self, process_id: str) -> ProcessSnapshot | None:
        return self._rows.get(process_id)

    def save(self, snapshot: ProcessSnapshot) -> None:
        validate_snapshot(snapshot)
        self._rows[snapshot.process_id] = snapshot

    def save_finding(self, process_id: str, finding: Finding) -> None:
        key = finding.evidence_group_id or finding.finding_id
        self._findings.setdefault(process_id, {})[key] = finding

    def load_findings(self, process_id: str) -> list[Finding]:
        return list(self._findings.get(process_id, {}).values())

    def clear(self) -> None:
        self._rows.clear()
        self._findings.clear()


UPSERT_PROCESS_SQL = """
INSERT INTO processes (
    id, object_id, process_state, scenario,
    matrix_version, model_version, dataset_version,
    parse_attempts, sync_attempts, sync_state,
    last_error_code, finalized_by, finalized_at, protocol_id, updated_at
) VALUES (
    %(id)s, %(object_id)s, %(process_state)s, %(scenario)s,
    %(matrix_version)s, %(model_version)s, %(dataset_version)s,
    %(parse_attempts)s, %(sync_attempts)s, %(sync_state)s,
    %(last_error_code)s, %(finalized_by)s, %(finalized_at)s, %(protocol_id)s, now()
)
ON CONFLICT (id) DO UPDATE SET
    process_state = EXCLUDED.process_state,
    scenario = EXCLUDED.scenario,
    parse_attempts = EXCLUDED.parse_attempts,
    sync_attempts = EXCLUDED.sync_attempts,
    sync_state = EXCLUDED.sync_state,
    last_error_code = EXCLUDED.last_error_code,
    finalized_by = EXCLUDED.finalized_by,
    finalized_at = EXCLUDED.finalized_at,
    protocol_id = EXCLUDED.protocol_id,
    updated_at = now()
"""

ENSURE_OBJECT_SQL = """
INSERT INTO objects (id, name) VALUES (%(id)s, %(name)s)
ON CONFLICT (id) DO NOTHING
"""

PLACEHOLDER_PROTOCOL_SQL = """
INSERT INTO protocols (
    id, object_id, version, matrix_version, dataset_version, model_version,
    input_manifest_hash, status, payload, finalized_at
) VALUES (
    %(id)s, %(object_id)s, 1, %(matrix_version)s, %(dataset_version)s,
    %(model_version)s, %(input_manifest_hash)s, 'PROTOCOL_FINALIZED',
    %(payload)s::jsonb, %(finalized_at)s
)
ON CONFLICT (id) DO NOTHING
"""


def snapshot_params(snapshot: ProcessSnapshot) -> dict[str, object]:
    if snapshot.process_state is ProcessState.FINALIZED:
        finalized_at: datetime | None = datetime.now(tz=UTC)
    else:
        finalized_at = None
    return {
        "id": snapshot.process_id,
        "object_id": snapshot.object_id,
        "process_state": snapshot.process_state.value,
        "scenario": snapshot.scenario.value,
        "matrix_version": snapshot.matrix_version,
        "model_version": snapshot.model_version,
        "dataset_version": snapshot.dataset_version,
        "parse_attempts": snapshot.parse_attempts,
        "sync_attempts": snapshot.sync_attempts,
        "sync_state": snapshot.sync_state.value,
        "last_error_code": snapshot.last_error_code,
        "finalized_by": snapshot.finalized_by,
        "finalized_at": finalized_at,
        "protocol_id": snapshot.protocol_id,
        "name": snapshot.object_id,
        "input_manifest_hash": "pending",
        "payload": '{"kind":"internal_placeholder","assembled":false}',
    }


class PostgresProcessStore:
    """Пишет в schema.sql. psycopg — extra `store`, не обязательная зависимость pytest."""

    def __init__(self, connection: object) -> None:
        self._connection = connection

    def load(self, process_id: str) -> ProcessSnapshot | None:
        cursor = self._connection.execute(  # type: ignore[attr-defined]
            "SELECT id, object_id, process_state, scenario, matrix_version, "
            "model_version, dataset_version, parse_attempts, sync_attempts, "
            "sync_state, last_error_code, finalized_by, protocol_id "
            "FROM processes WHERE id = %(id)s",
            {"id": process_id},
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ProcessSnapshot(
            process_id=str(row[0]),
            object_id=str(row[1]),
            process_state=ProcessState(str(row[2])),
            scenario=Scenario(str(row[3])),
            matrix_version=str(row[4]),
            model_version=str(row[5]),
            dataset_version=None if row[6] is None else str(row[6]),
            parse_attempts=int(row[7]),
            sync_attempts=int(row[8]),
            sync_state=SyncState(str(row[9])),
            last_error_code=None if row[10] is None else str(row[10]),
            finalized_by=None if row[11] is None else str(row[11]),
            protocol_id=None if row[12] is None else str(row[12]),
        )

    def save(self, snapshot: ProcessSnapshot) -> None:
        validate_snapshot(snapshot)
        params = snapshot_params(snapshot)
        self._connection.execute(ENSURE_OBJECT_SQL, params)  # type: ignore[attr-defined]
        if snapshot.process_state is ProcessState.FINALIZED and snapshot.protocol_id:
            self._connection.execute(PLACEHOLDER_PROTOCOL_SQL, params)  # type: ignore[attr-defined]
        self._connection.execute(UPSERT_PROCESS_SQL, params)  # type: ignore[attr-defined]

    def save_finding(self, process_id: str, finding: Finding) -> None:
        del process_id, finding

    def load_findings(self, process_id: str) -> list[Finding]:
        del process_id
        return []
