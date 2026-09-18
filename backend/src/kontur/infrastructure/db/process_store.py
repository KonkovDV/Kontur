"""Снимок процесса по таблицам schema.sql (ТЗ п. 9.1, RT-2609-27).

`processes` держит состояние, комплектность и манифест. Очередь инспектора —
`process_findings`, файлы — `process_files`, журнал — `audit_log`.
Протокол ТЗ по-прежнему не выдумывается: placeholder нужен только CHECK
`finalized_needs_human` (protocol_id NOT NULL при FINALIZED).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from kontur.domain.models import DocStage, Finding, InspectorDecision
from kontur.domain.statuses import (
    Completeness,
    DisagreementKind,
    FindingStatus,
    ProcessState,
    ReasonCode,
    ReviewPriority,
    Scenario,
    SyncState,
)
from kontur.infrastructure.db.audit_store import AuditEvent, PostgresAuditStore

MAX_PARSE_ATTEMPTS = 3
MAX_SYNC_ATTEMPTS = 4


@dataclass(frozen=True, slots=True)
class FileRecord:
    file_id: str
    file_hash: str
    filename: str
    doc_stage: DocStage
    size_bytes: int


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
    completeness_pd: Completeness = Completeness.MISSING
    completeness_rd: Completeness = Completeness.MISSING
    completeness_id: Completeness = Completeness.MISSING
    input_manifest_hash: str = "pending"
    files: tuple[FileRecord, ...] = ()


class ProcessStore(Protocol):
    def load(self, process_id: str) -> ProcessSnapshot | None: ...

    def save(self, snapshot: ProcessSnapshot) -> None: ...

    def save_finding(self, process_id: str, finding: Finding) -> None: ...

    def load_findings(self, process_id: str) -> list[Finding]: ...

    def save_audit_event(
        self,
        process_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, object],
        *,
        object_id: str | None = None,
    ) -> None: ...

    def load_audit(self, process_id: str) -> list[AuditEvent]: ...


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


def finding_to_params(process_id: str, finding: Finding) -> dict[str, object]:
    decision = finding.inspector_decision
    payload = {
        "source_id": finding.source_id,
        "evidence_refs": list(finding.evidence_refs),
        "disagreement_kind": (
            None if finding.disagreement_kind is None else finding.disagreement_kind.value
        ),
        "llm_draft": finding.llm_draft,
        "expected_value": finding.expected_value,
        "actual_value": finding.actual_value,
        "delta": finding.delta,
    }
    return {
        "process_id": process_id,
        "store_key": finding.evidence_group_id or finding.finding_id,
        "finding_id": finding.finding_id,
        "evidence_group_id": finding.evidence_group_id,
        "rule_code": finding.rule_code,
        "finding_status": finding.finding_status.value,
        "review_priority": finding.review_priority.value,
        "matrix_version": finding.matrix_version,
        "rule_version": finding.rule_version,
        "model_version": finding.model_version,
        "expected_value": None if finding.expected_value is None else str(finding.expected_value),
        "actual_value": None if finding.actual_value is None else str(finding.actual_value),
        "delta": None if finding.delta is None else str(finding.delta),
        "rationale": finding.rationale,
        "inspector_id": None if decision is None else decision.inspector_id,
        "inspector_action": None if decision is None else decision.action,
        "reason_code": (
            None if decision is None or decision.reason_code is None else decision.reason_code.value
        ),
        "comment": None if decision is None else decision.comment,
        "decided_at": None if decision is None else decision.timestamp,
        "payload": json.dumps(payload, ensure_ascii=False),
    }


def _payload_dict(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, str):
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            return {str(key): value for key, value in loaded.items()}
    raise TypeError("finding payload")


def _as_scalar(raw: object) -> str | float | bool | None:
    if raw is None or isinstance(raw, str | float | bool):
        return raw
    return str(raw)


def finding_from_row(row: object) -> Finding:
    """Собрать Finding из строки SELECT process_findings (20 полей)."""

    cells: tuple[object, ...] = tuple(row)  # type: ignore[arg-type]
    extra = _payload_dict(cells[19])
    decision = None
    inspector_id = None if cells[14] is None else str(cells[14])
    if inspector_id:
        reason_raw = cells[16]
        stamp = cells[18]
        if not isinstance(stamp, datetime):
            stamp = datetime.now(tz=UTC)
        comment = None if cells[17] is None else str(cells[17])
        decision = InspectorDecision(
            inspector_id=inspector_id,
            action="" if cells[15] is None else str(cells[15]),
            timestamp=stamp,
            reason_code=None if reason_raw is None else ReasonCode(str(reason_raw)),
            comment=comment,
        )
    kind_raw = extra.get("disagreement_kind")
    refs_raw = extra.get("evidence_refs") or ()
    refs = tuple(str(item) for item in refs_raw) if isinstance(refs_raw, list | tuple) else ()
    expected = extra.get("expected_value", cells[10])
    actual = extra.get("actual_value", cells[11])
    delta = extra.get("delta", cells[12])
    expected_value: str | float | bool | None = _as_scalar(expected)
    actual_value: str | float | bool | None = _as_scalar(actual)
    delta_raw = _as_scalar(delta)
    delta_value: str | float | None
    if isinstance(delta_raw, bool):
        delta_value = str(delta_raw)
    else:
        delta_value = delta_raw
    source_raw = extra.get("source_id")
    draft_raw = extra.get("llm_draft")
    group_raw = cells[3]
    return Finding(
        finding_id=str(cells[2]),
        rule_code=str(cells[4]),
        finding_status=FindingStatus(str(cells[5])),
        review_priority=ReviewPriority(str(cells[6])),
        matrix_version=str(cells[7]),
        rule_version=str(cells[8]),
        model_version=str(cells[9]),
        evidence_group_id=None if group_raw is None else str(group_raw),
        expected_value=expected_value,
        actual_value=actual_value,
        delta=delta_value,
        rationale="" if cells[13] is None else str(cells[13]),
        llm_draft=None if draft_raw is None else str(draft_raw),
        inspector_decision=decision,
        source_id=None if source_raw is None else str(source_raw),
        evidence_refs=refs,
        disagreement_kind=None if kind_raw is None else DisagreementKind(str(kind_raw)),
    )


class MemoryProcessStore:
    """Исполняемый DAO без Postgres: те же инварианты, что в schema.sql."""

    def __init__(self) -> None:
        self._rows: dict[str, ProcessSnapshot] = {}
        self._findings: dict[str, dict[str, Finding]] = {}
        self._audit: dict[str, list[AuditEvent]] = {}

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

    def save_audit_event(
        self,
        process_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, object],
        *,
        object_id: str | None = None,
    ) -> None:
        del object_id
        self._audit.setdefault(process_id, []).append((actor_id, action, payload))

    def load_audit(self, process_id: str) -> list[AuditEvent]:
        return list(self._audit.get(process_id, ()))

    def clear(self) -> None:
        self._rows.clear()
        self._findings.clear()
        self._audit.clear()


UPSERT_PROCESS_SQL = """
INSERT INTO processes (
    id, object_id, process_state, scenario,
    matrix_version, model_version, dataset_version,
    completeness_pd, completeness_rd, completeness_id, input_manifest_hash,
    parse_attempts, sync_attempts, sync_state,
    last_error_code, finalized_by, finalized_at, protocol_id, updated_at
) VALUES (
    %(id)s, %(object_id)s, %(process_state)s, %(scenario)s,
    %(matrix_version)s, %(model_version)s, %(dataset_version)s,
    %(completeness_pd)s, %(completeness_rd)s, %(completeness_id)s,
    %(input_manifest_hash)s,
    %(parse_attempts)s, %(sync_attempts)s, %(sync_state)s,
    %(last_error_code)s, %(finalized_by)s, %(finalized_at)s, %(protocol_id)s, now()
)
ON CONFLICT (id) DO UPDATE SET
    process_state = EXCLUDED.process_state,
    scenario = EXCLUDED.scenario,
    completeness_pd = EXCLUDED.completeness_pd,
    completeness_rd = EXCLUDED.completeness_rd,
    completeness_id = EXCLUDED.completeness_id,
    input_manifest_hash = EXCLUDED.input_manifest_hash,
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

UPSERT_FINDING_SQL = """
INSERT INTO process_findings (
    process_id, store_key, finding_id, evidence_group_id, rule_code,
    finding_status, review_priority, matrix_version, rule_version, model_version,
    expected_value, actual_value, delta, rationale,
    inspector_id, inspector_action, reason_code, comment, decided_at, payload
) VALUES (
    %(process_id)s, %(store_key)s, %(finding_id)s, %(evidence_group_id)s, %(rule_code)s,
    %(finding_status)s, %(review_priority)s, %(matrix_version)s, %(rule_version)s,
    %(model_version)s, %(expected_value)s, %(actual_value)s, %(delta)s, %(rationale)s,
    %(inspector_id)s, %(inspector_action)s, %(reason_code)s, %(comment)s,
    %(decided_at)s, %(payload)s::jsonb
)
ON CONFLICT (process_id, store_key) DO UPDATE SET
    finding_id = EXCLUDED.finding_id,
    evidence_group_id = EXCLUDED.evidence_group_id,
    rule_code = EXCLUDED.rule_code,
    finding_status = EXCLUDED.finding_status,
    review_priority = EXCLUDED.review_priority,
    expected_value = EXCLUDED.expected_value,
    actual_value = EXCLUDED.actual_value,
    delta = EXCLUDED.delta,
    rationale = EXCLUDED.rationale,
    inspector_id = EXCLUDED.inspector_id,
    inspector_action = EXCLUDED.inspector_action,
    reason_code = EXCLUDED.reason_code,
    comment = EXCLUDED.comment,
    decided_at = EXCLUDED.decided_at,
    payload = EXCLUDED.payload
"""

SELECT_FINDINGS_SQL = """
SELECT process_id, store_key, finding_id, evidence_group_id, rule_code,
       finding_status, review_priority, matrix_version, rule_version, model_version,
       expected_value, actual_value, delta, rationale,
       inspector_id, inspector_action, reason_code, comment, decided_at, payload
FROM process_findings
WHERE process_id = %(process_id)s
"""

DELETE_FILES_SQL = "DELETE FROM process_files WHERE process_id = %(id)s"

INSERT_FILE_SQL = """
INSERT INTO process_files (
    process_id, file_id, file_hash, filename, doc_stage, size_bytes
) VALUES (
    %(process_id)s, %(file_id)s, %(file_hash)s, %(filename)s, %(doc_stage)s, %(size_bytes)s
)
"""

SELECT_FILES_SQL = """
SELECT file_id, file_hash, filename, doc_stage, size_bytes
FROM process_files
WHERE process_id = %(process_id)s
ORDER BY file_id
"""

SELECT_PROCESS_SQL = """
SELECT id, object_id, process_state, scenario, matrix_version,
       model_version, dataset_version, parse_attempts, sync_attempts,
       sync_state, last_error_code, finalized_by, protocol_id,
       completeness_pd, completeness_rd, completeness_id, input_manifest_hash
FROM processes WHERE id = %(id)s
"""


def snapshot_params(snapshot: ProcessSnapshot) -> dict[str, object]:
    if snapshot.process_state is ProcessState.FINALIZED:
        finalized_at: datetime | None = datetime.now(tz=UTC)
    else:
        finalized_at = None
    manifest = snapshot.input_manifest_hash
    return {
        "id": snapshot.process_id,
        "object_id": snapshot.object_id,
        "process_state": snapshot.process_state.value,
        "scenario": snapshot.scenario.value,
        "matrix_version": snapshot.matrix_version,
        "model_version": snapshot.model_version,
        "dataset_version": snapshot.dataset_version,
        "completeness_pd": snapshot.completeness_pd.value,
        "completeness_rd": snapshot.completeness_rd.value,
        "completeness_id": snapshot.completeness_id.value,
        "input_manifest_hash": manifest,
        "parse_attempts": snapshot.parse_attempts,
        "sync_attempts": snapshot.sync_attempts,
        "sync_state": snapshot.sync_state.value,
        "last_error_code": snapshot.last_error_code,
        "finalized_by": snapshot.finalized_by,
        "finalized_at": finalized_at,
        "protocol_id": snapshot.protocol_id,
        "name": snapshot.object_id,
        "payload": '{"kind":"internal_placeholder","assembled":false}',
    }


class PostgresProcessStore:
    """Пишет в schema.sql. psycopg — extra `store`, не обязательная зависимость pytest."""

    def __init__(self, connection: object) -> None:
        self._connection = connection
        self._audit = PostgresAuditStore(connection)

    def load(self, process_id: str) -> ProcessSnapshot | None:
        cursor = self._connection.execute(  # type: ignore[attr-defined]
            SELECT_PROCESS_SQL,
            {"id": process_id},
        )
        row = cursor.fetchone()
        if row is None:
            return None
        files_cursor = self._connection.execute(  # type: ignore[attr-defined]
            SELECT_FILES_SQL, {"process_id": process_id}
        )
        files = tuple(
            FileRecord(
                file_id=str(item[0]),
                file_hash=str(item[1]).strip(),
                filename=str(item[2]),
                doc_stage=DocStage(str(item[3])),
                size_bytes=int(item[4]),
            )
            for item in files_cursor.fetchall()
        )
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
            completeness_pd=Completeness(str(row[13])),
            completeness_rd=Completeness(str(row[14])),
            completeness_id=Completeness(str(row[15])),
            input_manifest_hash=str(row[16]),
            files=files,
        )

    def save(self, snapshot: ProcessSnapshot) -> None:
        validate_snapshot(snapshot)
        params = snapshot_params(snapshot)
        self._connection.execute(ENSURE_OBJECT_SQL, params)  # type: ignore[attr-defined]
        if snapshot.process_state is ProcessState.FINALIZED and snapshot.protocol_id:
            self._connection.execute(PLACEHOLDER_PROTOCOL_SQL, params)  # type: ignore[attr-defined]
        self._connection.execute(UPSERT_PROCESS_SQL, params)  # type: ignore[attr-defined]
        self._connection.execute(DELETE_FILES_SQL, {"id": snapshot.process_id})  # type: ignore[attr-defined]
        for item in snapshot.files:
            self._connection.execute(  # type: ignore[attr-defined]
                INSERT_FILE_SQL,
                {
                    "process_id": snapshot.process_id,
                    "file_id": item.file_id,
                    "file_hash": item.file_hash,
                    "filename": item.filename,
                    "doc_stage": item.doc_stage.value,
                    "size_bytes": item.size_bytes,
                },
            )

    def save_finding(self, process_id: str, finding: Finding) -> None:
        params = finding_to_params(process_id, finding)
        self._connection.execute(UPSERT_FINDING_SQL, params)  # type: ignore[attr-defined]

    def load_findings(self, process_id: str) -> list[Finding]:
        cursor = self._connection.execute(  # type: ignore[attr-defined]
            SELECT_FINDINGS_SQL, {"process_id": process_id}
        )
        return [finding_from_row(row) for row in cursor.fetchall()]

    def save_audit_event(
        self,
        process_id: str,
        actor_id: str,
        action: str,
        payload: dict[str, object],
        *,
        object_id: str | None = None,
    ) -> None:
        self._audit.save_event(
            process_id, actor_id, action, payload, object_id=object_id
        )

    def load_audit(self, process_id: str) -> list[AuditEvent]:
        return self._audit.load_events(process_id)
