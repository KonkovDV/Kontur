"""Состояние процессов: снимок в DAO, очередь — в process_findings / audit_log.

Таблица `processes` хранит состояние и комплектность. HTTP по умолчанию держит
контур в памяти и пишет снимок в MemoryProcessStore. Postgres включает
адаптер с теми же таблицами schema.sql.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from uuid import uuid4

from kontur.application import review as review_actions
from kontur.application.process_pipeline import (
    PipelineFile,
    PipelineReport,
    run_process_pipeline,
    stamp_approval_from_pdf,
)
from kontur.application.protocol import (
    assemble_protocol,
    protocol_identity,
    reject_placeholder_payload,
)
from kontur.application.retry_policy import next_sync_attempt
from kontur.application.scenarios import CompletenessMap, detect_scenario
from kontur.domain.models import ApprovalStatus, DocStage, Finding
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
    FileRecord,
    MemoryProcessStore,
    ProcessSnapshot,
    ProcessStore,
)


class MemoryAudit:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []
        self._store: ProcessStore | None = None
        self._process_id: str | None = None
        self._object_id: str | None = None

    def bind(self, store: ProcessStore, process_id: str, object_id: str) -> None:
        self._store = store
        self._process_id = process_id
        self._object_id = object_id

    def record(self, actor_id: str, action: str, payload: dict[str, object]) -> None:
        self.records.append((actor_id, action, payload))
        if self._store is not None and self._process_id is not None:
            self._store.save_audit_event(
                self._process_id,
                actor_id,
                action,
                payload,
                object_id=self._object_id,
            )


@dataclass
class AcceptedFile:
    file_id: str
    file_hash: str
    filename: str
    doc_stage: DocStage
    size_bytes: int
    stamp_approval: ApprovalStatus = ApprovalStatus.UNKNOWN


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
    blobs: dict[str, bytes] = field(default_factory=dict)
    audit: MemoryAudit = field(default_factory=MemoryAudit)
    finalized_by: str | None = None
    matrix_version: str = "draft-0"
    model_version: str = "none"
    dataset_version: str = "unspecified"
    input_manifest_hash: str = "pending"
    git_sha: str = field(default_factory=lambda: os.environ.get("GITHUB_SHA") or "unspecified")
    last_sync_notice: str | None = None
    protocol_id: str | None = None
    inspector_approved_file_ids: set[str] = field(default_factory=set)

    def has_file(self, content_hash: str, stage: DocStage) -> bool:
        """True, если hash+stage уже прикреплены к процессу."""

        return any(
            item.file_hash == content_hash and item.doc_stage == stage
            for item in self.files
        )

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
    """Процессы в памяти плюс снимок DAO: находки, файлы, комплектность, аудит."""

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
            completeness_pd=record.completeness[DocStage.PD],
            completeness_rd=record.completeness[DocStage.RD],
            completeness_id=record.completeness[DocStage.ID],
            input_manifest_hash=record.input_manifest_hash,
            files=tuple(
                FileRecord(
                    file_id=item.file_id,
                    file_hash=item.file_hash,
                    filename=item.filename,
                    doc_stage=item.doc_stage,
                    size_bytes=item.size_bytes,
                )
                for item in record.files
            ),
        )

    def _persist(self, record: ProcessRecord) -> None:
        self._store.save(self._snapshot(record))

    def _hydrate(self, snapshot: ProcessSnapshot) -> ProcessRecord:
        return ProcessRecord(
            process_id=snapshot.process_id,
            object_id=snapshot.object_id,
            process_state=snapshot.process_state,
            completeness={
                DocStage.PD: snapshot.completeness_pd,
                DocStage.RD: snapshot.completeness_rd,
                DocStage.ID: snapshot.completeness_id,
            },
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
            input_manifest_hash=snapshot.input_manifest_hash,
            files=[
                AcceptedFile(
                    file_id=item.file_id,
                    file_hash=item.file_hash,
                    filename=item.filename,
                    doc_stage=item.doc_stage,
                    size_bytes=item.size_bytes,
                )
                for item in snapshot.files
            ],
        )

    def load_protocol(self, protocol_id: str) -> dict[str, object] | None:
        return self._store.load_protocol(protocol_id)

    def load_protocol_version(
        self, object_id: str, version: int
    ) -> dict[str, object] | None:
        return self._store.load_protocol_version(object_id, version)

    def _assemble_protocol_payload(
        self, record: ProcessRecord, *, protocol_id: str, version: int
    ) -> dict[str, object]:
        return assemble_protocol(
            protocol_id=protocol_id,
            object_id=record.object_id,
            findings=tuple(record.findings.values()),
            completeness=record.completeness,
            files=[
                {"file_id": item.file_id, "file_hash": item.file_hash}
                for item in record.files
            ],
            versions={
                "matrix_version": record.matrix_version,
                "model_version": record.model_version,
                "dataset_version": record.dataset_version,
                "git_sha": record.git_sha,
            },
            process_state=record.process_state,
            input_manifest_hash=record.input_manifest_hash,
            version=version,
        )

    def get(self, process_id: str) -> ProcessRecord | None:
        current = self._items.get(process_id)
        if current is not None:
            return current
        snapshot = self._store.load(process_id)
        if snapshot is None:
            return None
        record = self._hydrate(snapshot)
        for finding in self._store.load_findings(process_id):
            key = finding.evidence_group_id or finding.finding_id
            record.findings[key] = finding
        record.audit.records.extend(self._store.load_audit(process_id))
        record.audit.bind(self._store, process_id, record.object_id)
        record.inspector_approved_file_ids = {
            str(payload["file_id"])
            for _actor, action, payload in record.audit.records
            if action == "SELECT_REVISION" and isinstance(payload.get("file_id"), str)
        }
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
        record.audit.bind(self._store, record.process_id, record.object_id)
        self._persist(record)
        return record

    def reopen_for_upload(self, record: ProcessRecord) -> None:
        if record.process_state is ProcessState.FINALIZED:
            raise TransitionError("протокол финализирован, дозагрузка запрещена")
        if record.process_state is not ProcessState.PARSING:
            record.process_state = advance_process(record.process_state, ProcessState.PARSING)

    def attach_file(self, record: ProcessRecord, item: AcceptedFile) -> bool:
        """Прикрепить файл. Повтор hash+stage не дублирует (как UNIQUE в schema.sql)."""

        if record.has_file(item.file_hash, item.doc_stage):
            return False
        record.files.append(item)
        record.completeness[item.doc_stage] = Completeness.UPLOADED
        record.scenario = detect_scenario(record.completeness)
        record.input_manifest_hash = item.file_hash if len(record.files) == 1 else "pending"
        self._persist(record)
        return True

    def keep_blob(self, record: ProcessRecord, file_id: str, content: bytes) -> None:
        """Тело файла только в памяти процесса: Postgres снимок его не хранит."""

        record.blobs[file_id] = content

    def run_matrix_pipeline(self, record: ProcessRecord) -> PipelineReport:
        """L1–L7 по загруженным PDF. Успех прогона → READY, не FINALIZED."""

        report = run_process_pipeline(
            object_id=record.object_id,
            completeness=record.completeness,
            files=tuple(
                PipelineFile(
                    file_id=item.file_id,
                    file_hash=item.file_hash,
                    filename=item.filename,
                    doc_stage=item.doc_stage,
                )
                for item in record.files
            ),
            blobs=record.blobs,
            inspector_approved_file_ids=frozenset(record.inspector_approved_file_ids),
        )
        for item in record.files:
            stamp = report.stamp_by_file_id.get(item.file_id)
            if stamp is not None:
                item.stamp_approval = stamp
        for finding in report.findings:
            self.put_finding(record.process_id, finding)
        record.parse_attempts += 1
        record.audit.record(
            "system",
            "PIPELINE",
            {
                "rules_evaluated": report.rules_evaluated,
                "pages_built": report.pages_built,
                "parse_errors": len(report.parse_errors),
            },
        )
        if record.process_state is ProcessState.PARSING:
            record.process_state = advance_process(record.process_state, ProcessState.READY)
        self._persist(record)
        return report

    def put_finding(self, process_id: str, finding: Finding) -> None:
        """Сохранить находку. Повтор at-least-once с тем же evidence_group_id
        перезаписывает запись, а не создаёт дубликат (RT-G, stop-ship п. 11).

        Halted-находки без группы ключуются по finding_id.
        """
        record = self._items[process_id]
        key = finding.evidence_group_id or finding.finding_id
        record.findings[key] = finding
        self._store.save_finding(process_id, finding)

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
            stored_key: str | None = None
            current: Finding | None = None
            for key, item in record.findings.items():
                if item.finding_id == finding_id or key == finding_id:
                    stored_key = key
                    current = item
                    break
            if current is None or stored_key is None:
                continue
            updated = review_actions.review(
                current,
                actor=actor,
                action=action,
                reason_code=reason_code,
                comment=comment,
            )
            record.findings[stored_key] = updated
            self._store.save_finding(record.process_id, updated)
            record.audit.record(
                actor.actor_id,
                "REVIEW",
                {"finding_id": finding_id, "action": action},
            )
            if record.process_state is ProcessState.READY:
                record.process_state = review_actions.start_verification(
                    record.process_state, actor=actor, audit=record.audit
                )
                self._persist(record)
            return updated
        raise KeyError(finding_id)

    def _replace_machine_findings(
        self, record: ProcessRecord, findings: tuple[Finding, ...]
    ) -> None:
        record.findings.clear()
        for finding in findings:
            key = finding.evidence_group_id or finding.finding_id
            record.findings[key] = finding
        self._store.replace_findings(record.process_id, findings)

    def _pipeline_files(self, record: ProcessRecord) -> tuple[PipelineFile, ...]:
        return tuple(
            PipelineFile(
                file_id=item.file_id,
                file_hash=item.file_hash,
                filename=item.filename,
                doc_stage=item.doc_stage,
            )
            for item in record.files
        )

    def select_revision(
        self,
        process_id: str,
        file_id: str,
        *,
        actor: Actor,
        comment: str,
    ) -> ProcessRecord:
        """Инспектор назначает файл эталоном и пересчитывает матрицу."""

        record = self._items[process_id]
        if record.process_state is ProcessState.FINALIZED:
            raise TransitionError("протокол финализирован, выбор редакции запрещён")
        if record.process_state is not ProcessState.READY:
            raise TransitionError("выбор эталона только из READY")
        if any(item.inspector_decision is not None for item in record.findings.values()):
            raise TransitionError("очередь уже содержит решения инспектора")
        match = next((item for item in record.files if item.file_id == file_id), None)
        if match is None:
            raise KeyError(file_id)
        raw = record.blobs.get(file_id)
        if raw is None:
            raise TransitionError("нет содержимого файла; повторите загрузку")
        stamp = stamp_approval_from_pdf(
            raw,
            file_id=match.file_id,
            file_hash=match.file_hash,
            filename=match.filename,
        )
        match.stamp_approval = stamp
        review_actions.select_revision_as_etalon(
            actor=actor, stamp=stamp, comment=comment
        )
        record.inspector_approved_file_ids.add(file_id)
        record.audit.record(
            actor.actor_id,
            "SELECT_REVISION",
            {
                "file_id": file_id,
                "file_hash": match.file_hash,
                "doc_stage": match.doc_stage.value,
                "stamp_approval": stamp.value,
                "comment": comment.strip(),
            },
        )
        report = run_process_pipeline(
            object_id=record.object_id,
            completeness=record.completeness,
            files=self._pipeline_files(record),
            blobs=record.blobs,
            inspector_approved_file_ids=frozenset(record.inspector_approved_file_ids),
        )
        for item in record.files:
            recorded = report.stamp_by_file_id.get(item.file_id)
            if recorded is not None:
                item.stamp_approval = recorded
        self._replace_machine_findings(record, report.findings)
        record.parse_attempts += 1
        record.audit.record(
            "system",
            "PIPELINE",
            {
                "rules_evaluated": report.rules_evaluated,
                "pages_built": report.pages_built,
                "parse_errors": len(report.parse_errors),
                "after": "SELECT_REVISION",
            },
        )
        self._persist(record)
        return record

    def start_verification(self, process_id: str, actor: Actor) -> ProcessRecord:
        record = self._items[process_id]
        record.process_state = review_actions.start_verification(
            record.process_state, actor=actor, audit=record.audit
        )
        self._persist(record)
        return record

    def complete_verification(self, process_id: str, actor: Actor) -> ProcessRecord:
        record = self._items[process_id]
        record.process_state = review_actions.complete_verification(
            record.process_state,
            actor=actor,
            findings=list(record.findings.values()),
            audit=record.audit,
        )
        self._persist(record)
        return record

    def finalize(self, process_id: str, actor: Actor) -> ProcessRecord:
        record = self._items[process_id]
        previous_state = record.process_state
        previous_finalized_by = record.finalized_by
        previous_protocol_id = record.protocol_id
        audit_mark = len(record.audit.records)
        try:
            record.process_state = review_actions.finalize_process(
                record.process_state,
                actor=actor,
                findings=list(record.findings.values()),
                audit=record.audit,
            )
            record.finalized_by = actor.actor_id
            version = self._store.next_protocol_version(record.object_id)
            protocol_id = protocol_identity(record.process_id, version)
            payload = self._assemble_protocol_payload(
                record, protocol_id=protocol_id, version=version
            )
            reject_placeholder_payload(payload)
            record.protocol_id = protocol_id
            self._store.materialize_finalized(self._snapshot(record), payload)
        except Exception:
            record.process_state = previous_state
            record.finalized_by = previous_finalized_by
            record.protocol_id = previous_protocol_id
            del record.audit.records[audit_mark:]
            raise
        return record

    def unfinalize(self, process_id: str, actor: Actor, reason: str) -> ProcessRecord:
        record = self._items[process_id]
        if record.sync_state is not SyncState.NOT_REQUESTED:
            raise TransitionError("нельзя отменить протокол, пока идёт или ожидается выгрузка")
        record.process_state = review_actions.unfinalize_process(
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
