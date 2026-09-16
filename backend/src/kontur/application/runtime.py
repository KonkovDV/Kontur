"""Состояние процессов в памяти процесса API.

Это не Postgres: таблица `processes` — контракт хранения, этот модуль —
исполняемый контур для HTTP, пока нет DAO. После перезапуска процессы
пропадают — это честно, а не «состояние где-то в очереди».
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
    """In-memory процессы. Не переживает рестарт и не пишет в schema.sql."""

    def __init__(self) -> None:
        self._items: dict[str, ProcessRecord] = {}

    def reset(self) -> None:
        self._items.clear()

    def get(self, process_id: str) -> ProcessRecord | None:
        return self._items.get(process_id)

    def create(self, object_id: str, completeness: CompletenessMap) -> ProcessRecord:
        record = ProcessRecord(
            process_id=str(uuid4()),
            object_id=object_id,
            process_state=ProcessState.PARSING,
            completeness=completeness,
            scenario=detect_scenario(completeness),
        )
        self._items[record.process_id] = record
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
        return record

    def request_sync(self, process_id: str) -> ProcessRecord:
        record = self._items[process_id]
        if record.process_state is not ProcessState.FINALIZED:
            raise TransitionError("во внешнюю ИС уходит только финализированный протокол")
        if record.sync_state is SyncState.NOT_REQUESTED:
            record.sync_state = SyncState.PENDING_SYNC
            record.last_sync_notice = "передача поставлена в очередь; РиН не вызывался"
            return record
        record.sync_attempts += 1
        decision = next_sync_attempt(max(record.sync_attempts, 1))
        record.sync_state = decision.state
        record.last_sync_notice = decision.reason
        return record
