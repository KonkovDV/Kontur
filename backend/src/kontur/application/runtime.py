"""Состояние процессов: снимок в DAO, находки — в памяти процесса API.

Таблица `processes` — контракт хранения. HTTP по умолчанию держит полный
контур в памяти и пишет снимок в MemoryProcessStore. Postgres включается
отдельным адаптером; находки и комплектность после рестарта не восстанавливаются.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import uuid4

from kontur.application.retry_policy import next_sync_attempt
from kontur.application.review import finalize_process, review, unfinalize_process
from kontur.application.scenarios import CompletenessMap, detect_scenario
from kontur.domain.models import DocStage, Finding
from kontur.domain.state_machines import Actor, TransitionError, advance_process
from kontur.domain.status_map import protocol_status, tz_upload_status
from kontur.domain.statuses import (
    Completeness,
    FindingStatus,
    ProcessState,
    ReasonCode,
    Scenario,
    SyncState,
)
from kontur.infrastructure.db.process_store import (
    MemoryProcessStore,
    ProcessSnapshot,
    ProcessStore,
)


def _empty_completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


class MemoryAudit:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def record(self, actor_id: str, action: str, payload: dict[str, object]) -> None:
        self.records.append((actor_id, action, payload))


@dataclass
class AcceptedFile:
    file_id: str
    file_hash: str
    filename: str
    doc_stage: DocStage
    size_bytes: int


@dataclass
class ProcessRecord:
    process_id: str
    object_id: str
    process_state: ProcessState
    completeness: CompletenessMap
    scenario: Scenario
    sync_state: SyncState = SyncState.NOT_REQUESTED
    sync_attempts: int = 0
    parse_attempts: int = 0
    findings: dict[str, Finding] = field(default_factory=dict)
    files: list[AcceptedFile] = field(default_factory=list)
    audit: MemoryAudit = field(default_factory=MemoryAudit)
    finalized_by: str | None = None
    matrix_version: str = "draft-0"
    model_version: str = "none"
    dataset_version: str = "unspecified"
    input_manifest_hash: str = "pending"
    git_sha: str = field(default_factory=lambda: os.environ.get("GITHUB_SHA") or "unspecified")
    last_sync_notice: str | None = None
    protocol_id: str | None = None

    def to_status(self) -> dict[str, object]:
        counters = {
            "candidates": 0,
            "confirmed_violations": 0,
            "negative_verified": 0,
            "missing_evidence": 0,
            "clarification_required": 0,
            "suspicions": 0,
        }
        for finding in self.findings.values():
            if finding.finding_status is FindingStatus.CANDIDATE:
                counters["candidates"] += 1
            elif finding.finding_status is FindingStatus.CONFIRMED_VIOLATION:
                counters["confirmed_violations"] += 1
            elif finding.finding_status is FindingStatus.NEGATIVE_VERIFIED:
                counters["negative_verified"] += 1
            elif finding.finding_status is FindingStatus.MISSING_EVIDENCE:
                counters["missing_evidence"] += 1
            elif finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED:
                counters["clarification_required"] += 1
            elif finding.finding_status is FindingStatus.SUSPICION:
                counters["suspicions"] += 1
        return {
            "process_id": self.process_id,
            "process_state": self.process_state.value,
            "scenario": self.scenario.value,
            "completeness": {
                "pd": tz_upload_status(DocStage.PD, self.completeness[DocStage.PD]),
                "rd": tz_upload_status(DocStage.RD, self.completeness[DocStage.RD]),
                "id": tz_upload_status(DocStage.ID, self.completeness[DocStage.ID]),
            },
            "protocol_status": protocol_status(self.process_state),
            "counters": counters,
            "sync_state": self.sync_state.value,
            "versions": {
                "matrix_version": self.matrix_version,
                "model_version": self.model_version,
                "dataset_version": self.dataset_version,
                "input_manifest_hash": self.input_manifest_hash,
                "git_sha": self.git_sha,
            },
        }


class ProcessWorkspace:
    """Процессы в памяти плюс снимок DAO. Находки после рестарта не восстанавливаются."""

    def __init__(self, store: ProcessStore | None = None) -> None:
        self._items: dict[str, ProcessRecord] = {}
        self._store: ProcessStore = store if store is not None else MemoryProcessStore()

    def reset(self) -> None:
        self._items.clear()
        store = self._store
        if isinstance(store, MemoryProcessStore):
            store.clear()

    def _snapshot(self, record: ProcessRecord) -> ProcessSnapshot:
        return ProcessSnapshot(
            process_id=record.process_id,
            object_id=record.object_id,
            process_state=record.process_state,
            scenario=record.scenario,
            matrix_version=record.matrix_version,
            model_version=record.model_version,
            dataset_version=record.dataset_version,
            parse_attempts=record.parse_attempts,
            sync_attempts=record.sync_attempts,
            sync_state=record.sync_state,
            last_error_code=record.last_sync_notice,
            finalized_by=record.finalized_by,
            protocol_id=record.protocol_id,
        )

    def _persist(self, record: ProcessRecord) -> None:
        self._store.save(self._snapshot(record))

    def _hydrate(self, snapshot: ProcessSnapshot) -> ProcessRecord:
        return ProcessRecord(
            process_id=snapshot.process_id,
            object_id=snapshot.object_id,
            process_state=snapshot.process_state,
            completeness=_empty_completeness(),
            scenario=snapshot.scenario,
            sync_state=snapshot.sync_state,
            sync_attempts=snapshot.sync_attempts,
            parse_attempts=snapshot.parse_attempts,
            finalized_by=snapshot.finalized_by,
            matrix_version=snapshot.matrix_version,
            model_version=snapshot.model_version,
            dataset_version=snapshot.dataset_version or "unspecified",
            last_sync_notice=snapshot.last_error_code,
            protocol_id=snapshot.protocol_id,
        )

    def get(self, process_id: str) -> ProcessRecord | None:
        current = self._items.get(process_id)
        if current is not None:
            return current
        snapshot = self._store.load(process_id)
        if snapshot is None:
            return None
        record = self._hydrate(snapshot)
        self._items[process_id] = record
        return record

    def create(self, object_id: str, completeness: CompletenessMap) -> ProcessRecord:
        record = ProcessRecord(
            process_id=str(uuid4()),
            object_id=object_id,
            process_state=ProcessState.PARSING,
            completeness=completeness,
            scenario=detect_scenario(completeness),
        )
        self._items[record.process_id] = record
        self._persist(record)
        return record

    def reopen_for_upload(self, record: ProcessRecord) -> None:
        if record.process_state is ProcessState.FINALIZED:
            raise TransitionError("протокол финализирован, дозагрузка запрещена")
        if record.process_state is not ProcessState.PARSING:
            record.process_state = advance_process(record.process_state, ProcessState.PARSING)

    def attach_file(self, record: ProcessRecord, item: AcceptedFile) -> None:
        record.files.append(item)
        record.completeness[item.doc_stage] = Completeness.UPLOADED
        record.scenario = detect_scenario(record.completeness)
        record.input_manifest_hash = item.file_hash if len(record.files) == 1 else "pending"

    def put_finding(self, process_id: str, finding: Finding) -> None:
        record = self._items[process_id]
        record.findings[finding.finding_id] = finding

    def review_finding(
        self,
        finding_id: str,
        *,
        actor: Actor,
        action: str,
        reason_code: ReasonCode | None,
        comment: str,
    ) -> Finding:
        for record in self._items.values():
            current = record.findings.get(finding_id)
            if current is None:
                continue
            updated = review(
                current,
                actor=actor,
                action=action,
                reason_code=reason_code,
                comment=comment,
            )
            record.findings[finding_id] = updated
            record.audit.record(
                actor.actor_id,
                "REVIEW",
                {"finding_id": finding_id, "action": action},
            )
            return updated
        raise KeyError(finding_id)

    def finalize(self, process_id: str, actor: Actor) -> ProcessRecord:
        record = self._items[process_id]
        record.process_state = finalize_process(
            record.process_state,
            actor=actor,
            findings=list(record.findings.values()),
            audit=record.audit,
        )
        record.finalized_by = actor.actor_id
        record.protocol_id = record.protocol_id or f"placeholder-{record.process_id}"
        self._persist(record)
        return record

    def unfinalize(self, process_id: str, actor: Actor, reason: str) -> ProcessRecord:
        record = self._items[process_id]
        if record.sync_state is not SyncState.NOT_REQUESTED:
            raise TransitionError("нельзя отменить протокол, пока идёт или ожидается выгрузка")
        record.process_state = unfinalize_process(
            record.process_state,
            actor=actor,
            reason=reason,
            audit=record.audit,
        )
        record.finalized_by = None
        record.protocol_id = None
        self._persist(record)
        return record

    def request_sync(self, process_id: str) -> ProcessRecord:
        record = self._items[process_id]
        if record.process_state is not ProcessState.FINALIZED:
            raise TransitionError("во внешнюю ИС уходит только финализированный протокол")
        if record.sync_state is SyncState.NOT_REQUESTED:
            record.sync_state = SyncState.PENDING_SYNC
            record.last_sync_notice = "передача поставлена в очередь; РиН не вызывался"
            self._persist(record)
            return record
        record.sync_attempts += 1
        decision = next_sync_attempt(max(record.sync_attempts, 1))
        record.sync_state = decision.state
        record.last_sync_notice = decision.reason
        self._persist(record)
        return record
