"""DAO процессов: инварианты schema.sql без живого Postgres в pytest."""

from __future__ import annotations

import pytest

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage, Finding
from kontur.domain.state_machines import Actor
from kontur.domain.statuses import (
    Completeness,
    FindingStatus,
    ProcessState,
    ReasonCode,
    ReviewPriority,
    Scenario,
    SyncState,
)
from kontur.infrastructure.db.process_store import (
    ENSURE_OBJECT_SQL,
    PLACEHOLDER_PROTOCOL_SQL,
    SELECT_FINDINGS_SQL,
    UPSERT_FINDING_SQL,
    UPSERT_PROCESS_SQL,
    MemoryProcessStore,
    PostgresProcessStore,
    ProcessSnapshot,
    finding_from_row,
    finding_to_params,
    snapshot_params,
    validate_snapshot,
)


def _completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _snap(**overrides: object) -> ProcessSnapshot:
    payload: dict[str, object] = {
        "process_id": "p-1",
        "object_id": "obj-1",
        "process_state": ProcessState.PARSING,
        "scenario": Scenario.SINGLE_ONLY,
        "matrix_version": "draft-0",
        "model_version": "none",
    }
    payload.update(overrides)
    return ProcessSnapshot(**payload)  # type: ignore[arg-type]


def test_memory_store_roundtrip() -> None:
    store = MemoryProcessStore()
    store.save(_snap())
    loaded = store.load("p-1")
    assert loaded is not None
    assert loaded.process_state is ProcessState.PARSING


def test_finalized_without_human_is_rejected() -> None:
    with pytest.raises(ValueError, match="finalized_by"):
        validate_snapshot(_snap(process_state=ProcessState.FINALIZED, protocol_id="pr-1"))


def test_sync_before_finalize_is_rejected() -> None:
    with pytest.raises(ValueError, match="FINALIZED"):
        validate_snapshot(_snap(sync_state=SyncState.PENDING_SYNC))


def test_parse_attempts_are_capped() -> None:
    with pytest.raises(ValueError, match="parse_attempts"):
        validate_snapshot(_snap(parse_attempts=4))


def test_sql_matches_schema_columns() -> None:
    assert "INSERT INTO processes" in UPSERT_PROCESS_SQL
    assert "completeness_pd" in UPSERT_PROCESS_SQL
    assert "ON CONFLICT (id) DO UPDATE" in UPSERT_PROCESS_SQL
    assert "INSERT INTO objects" in ENSURE_OBJECT_SQL
    assert "PROTOCOL_FINALIZED" in PLACEHOLDER_PROTOCOL_SQL
    assert "INSERT INTO process_findings" in UPSERT_FINDING_SQL
    assert "FROM process_findings" in SELECT_FINDINGS_SQL
    assert "assembled" in str(snapshot_params(_snap()).get("payload"))


def test_workspace_survives_new_process_on_same_store() -> None:
    store = MemoryProcessStore()
    first = ProcessWorkspace(store=store)
    created = first.create("obj-1", _completeness())
    process_id = created.process_id
    second = ProcessWorkspace(store=store)
    loaded = second.get(process_id)
    assert loaded is not None
    assert loaded.process_state is ProcessState.PARSING
    assert loaded.object_id == "obj-1"
    assert loaded.findings == {}


def _candidate() -> Finding:
    return Finding(
        finding_id="f-persist",
        evidence_group_id="eg-persist",
        rule_code="PZ-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
    )


def test_findings_survive_new_workspace_on_same_store() -> None:
    store = MemoryProcessStore()
    first = ProcessWorkspace(store=store)
    created = first.create("obj-1", _completeness())
    first.put_finding(created.process_id, _candidate())
    second = ProcessWorkspace(store=store)
    loaded = second.get(created.process_id)
    assert loaded is not None
    stored = next(iter(loaded.findings.values()))
    assert stored.finding_id == "f-persist"
    assert stored.finding_status is FindingStatus.CANDIDATE
    assert loaded.completeness[DocStage.PD] is Completeness.UPLOADED


def test_reviewed_finding_survives_new_workspace() -> None:
    store = MemoryProcessStore()
    first = ProcessWorkspace(store=store)
    created = first.create("obj-1", _completeness())
    first.put_finding(created.process_id, _candidate())
    first.review_finding(
        "f-persist",
        actor=Actor(actor_id="insp-7", is_human=True),
        action="REJECT",
        reason_code=ReasonCode.OCR_ERROR,
        comment="ошибка чтения",
    )
    second = ProcessWorkspace(store=store)
    loaded = second.get(created.process_id)
    assert loaded is not None
    stored = next(iter(loaded.findings.values()))
    assert stored.finding_status is FindingStatus.NEGATIVE_VERIFIED


def test_attach_file_is_idempotent_on_hash_and_stage() -> None:
    workspace = ProcessWorkspace()
    record = workspace.create("obj-1", _completeness())
    item = AcceptedFile(
        file_id="file-1",
        file_hash="a" * 64,
        filename="pz.pdf",
        doc_stage=DocStage.PD,
        size_bytes=12,
    )
    retry = AcceptedFile(
        file_id="file-2",
        file_hash="a" * 64,
        filename="pz.pdf",
        doc_stage=DocStage.PD,
        size_bytes=12,
    )
    other_stage = AcceptedFile(
        file_id="file-3",
        file_hash="a" * 64,
        filename="rd.pdf",
        doc_stage=DocStage.RD,
        size_bytes=12,
    )
    assert workspace.attach_file(record, item) is True
    assert workspace.attach_file(record, retry) is False
    assert workspace.attach_file(record, other_stage) is True
    assert len(record.files) == 2


def test_files_completeness_and_audit_survive_new_workspace() -> None:
    store = MemoryProcessStore()
    first = ProcessWorkspace(store=store)
    created = first.create("obj-1", _completeness())
    first.attach_file(
        created,
        AcceptedFile(
            file_id="file-1",
            file_hash="b" * 64,
            filename="pz.pdf",
            doc_stage=DocStage.PD,
            size_bytes=12,
        ),
    )
    first.put_finding(created.process_id, _candidate())
    first.review_finding(
        "f-persist",
        actor=Actor(actor_id="insp-7", is_human=True),
        action="REJECT",
        reason_code=ReasonCode.OCR_ERROR,
        comment="ошибка чтения",
    )
    second = ProcessWorkspace(store=store)
    loaded = second.get(created.process_id)
    assert loaded is not None
    assert loaded.completeness[DocStage.PD] is Completeness.UPLOADED
    assert len(loaded.files) == 1
    assert loaded.files[0].file_hash == "b" * 64
    assert "REVIEW" in [event[1] for event in loaded.audit.records]


def test_finding_codec_roundtrip_keeps_inspector_reject() -> None:
    store = MemoryProcessStore()
    workspace = ProcessWorkspace(store=store)
    created = workspace.create("obj-1", _completeness())
    workspace.put_finding(created.process_id, _candidate())
    reviewed = workspace.review_finding(
        "f-persist",
        actor=Actor(actor_id="insp-7", is_human=True),
        action="REJECT",
        reason_code=ReasonCode.OCR_ERROR,
        comment="ошибка чтения",
    )
    params = finding_to_params(created.process_id, reviewed)
    row = (
        params["process_id"],
        params["store_key"],
        params["finding_id"],
        params["evidence_group_id"],
        params["rule_code"],
        params["finding_status"],
        params["review_priority"],
        params["matrix_version"],
        params["rule_version"],
        params["model_version"],
        params["expected_value"],
        params["actual_value"],
        params["delta"],
        params["rationale"],
        params["inspector_id"],
        params["inspector_action"],
        params["reason_code"],
        params["comment"],
        params["decided_at"],
        params["payload"],
    )
    restored = finding_from_row(row)
    assert restored.finding_status is FindingStatus.NEGATIVE_VERIFIED
    assert restored.inspector_decision is not None
    assert restored.inspector_decision.action == "REJECT"
    assert restored.inspector_decision.reason_code is ReasonCode.OCR_ERROR


class _Cursor:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def fetchone(self) -> object | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[object]:
        return list(self._rows)


class _Conn:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.findings: list[object] = []
        self.files: list[object] = []
        self.process: object | None = None
        self.audit: list[object] = []

    def execute(self, sql: str, params: object = None) -> _Cursor:
        del params
        self.sql.append(sql)
        text = " ".join(sql.split()).lower()
        if text.startswith("select") and "from processes" in text:
            return _Cursor([] if self.process is None else [self.process])
        if "from process_files" in text:
            return _Cursor(self.files)
        if "from process_findings" in text:
            return _Cursor(self.findings)
        if "from audit_log" in text:
            return _Cursor(self.audit)
        return _Cursor([])


def test_postgres_store_writes_findings_and_audit() -> None:
    conn = _Conn()
    store = PostgresProcessStore(conn)
    store.save(_snap())
    joined = "\n".join(conn.sql)
    assert "INSERT INTO processes" in joined
    assert "completeness_pd" in joined
    store.save_finding("p-1", _candidate())
    assert any("INSERT INTO process_findings" in item for item in conn.sql)
    params = finding_to_params("p-1", _candidate())
    conn.findings = [
        (
            params["process_id"],
            params["store_key"],
            params["finding_id"],
            params["evidence_group_id"],
            params["rule_code"],
            params["finding_status"],
            params["review_priority"],
            params["matrix_version"],
            params["rule_version"],
            params["model_version"],
            params["expected_value"],
            params["actual_value"],
            params["delta"],
            params["rationale"],
            params["inspector_id"],
            params["inspector_action"],
            params["reason_code"],
            params["comment"],
            params["decided_at"],
            params["payload"],
        )
    ]
    loaded = store.load_findings("p-1")
    assert loaded[0].finding_id == "f-persist"
    store.save_audit_event("p-1", "insp-7", "REVIEW", {"action": "REJECT"}, object_id="obj-1")
    assert any("INSERT INTO audit_log" in item for item in conn.sql)
