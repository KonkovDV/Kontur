"""DAO процессов: инварианты schema.sql без живого Postgres в pytest."""

from __future__ import annotations

from contextlib import contextmanager

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
    INSERT_PROTOCOL_SQL,
    SELECT_FINDINGS_SQL,
    UPSERT_FINDING_SQL,
    UPSERT_PROCESS_SQL,
    MemoryProcessStore,
    PostgresProcessStore,
    ProcessSnapshot,
    ProtocolConflictError,
    ProtocolMaterializationRequiredError,
    TransactionUnavailableError,
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
    assert "INSERT INTO process_findings" in UPSERT_FINDING_SQL
    assert "FROM process_findings" in SELECT_FINDINGS_SQL
    assert "payload" not in snapshot_params(_snap())
    assert "INSERT INTO protocols" in INSERT_PROTOCOL_SQL
    assert "ON CONFLICT (id) DO NOTHING" in INSERT_PROTOCOL_SQL
    assert "payload_sha256" in INSERT_PROTOCOL_SQL


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
    assert record.has_file("a" * 64, DocStage.PD) is True
    assert workspace.attach_file(record, retry) is False
    assert workspace.attach_file(record, other_stage) is True
    assert record.has_file("a" * 64, DocStage.RD) is True
    assert record.has_file("b" * 64, DocStage.PD) is False
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


class _UniqueViolation(Exception):
    sqlstate = "23505"


class _Conn:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.findings: list[object] = []
        self.files: list[object] = []
        self.process: object | None = None
        self.audit: list[object] = []
        self.saw_transaction = False
        self.in_transaction = False
        self.protocol_insert_rows: list[object] | None = [("protocol-p-1",)]
        self.existing_payload: object | None = None
        self.max_version = 0
        self.raise_unique = False

    @contextmanager
    def transaction(self):
        self.saw_transaction = True
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False

    def execute(self, sql: str, params: object = None) -> _Cursor:
        del params
        self.sql.append(sql)
        text = " ".join(sql.split()).lower()
        if self.raise_unique and "insert into protocols" in text:
            raise _UniqueViolation()
        if "insert into protocols" in text:
            if self.protocol_insert_rows is None:
                return _Cursor([])
            return _Cursor(list(self.protocol_insert_rows))
        if "from protocols" in text and "for update" in text:
            if self.existing_payload is None:
                return _Cursor([])
            return _Cursor([(self.existing_payload,)])
        if "max(version)" in text:
            return _Cursor([(self.max_version,)])
        if "from protocols" in text:
            if self.existing_payload is None:
                return _Cursor([])
            return _Cursor([(self.existing_payload,)])
        if text.startswith("select") and "from processes" in text:
            return _Cursor([] if self.process is None else [self.process])
        if "from process_files" in text:
            return _Cursor(self.files)
        if "from process_findings" in text:
            return _Cursor(self.findings)
        if "from audit_log" in text:
            return _Cursor(self.audit)
        return _Cursor([])


class _NoTxConn:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str, params: object = None) -> _Cursor:
        del params
        self.sql.append(sql)
        return _Cursor([])


def _final_payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "protocol_id": "protocol-p-1",
        "object_id": "obj-1",
        "version": 1,
        "status": "PROTOCOL_FINALIZED",
        "scenario": "SINGLE_ONLY",
        "upload_status": {
            "pd": "PD_UPLOADED",
            "rd": "RD_MISSING",
            "id": "ID_MISSING",
        },
        "sections": {
            "completeness": [],
            "candidates": [],
            "confirmed": [],
            "negative_verified": [],
            "suspicions": [],
        },
        "violation_count": 0,
        "versions": {
            "matrix_version": "draft-0",
            "model_version": "none",
            "dataset_version": "unspecified",
        },
        "input_manifest": {"manifest_hash": "pending", "files": []},
    }
    body.update(overrides)
    return body


def test_postgres_finalized_save_fails_closed_before_any_sql() -> None:
    conn = _Conn()
    store = PostgresProcessStore(conn)
    finalized = _snap(
        process_state=ProcessState.FINALIZED,
        finalized_by="insp-7",
        protocol_id="proto-1",
    )

    with pytest.raises(
        ProtocolMaterializationRequiredError,
        match="atomic versioned protocol materialization",
    ):
        store.save(finalized)

    assert conn.sql == []


def test_memory_store_keeps_finalized_snapshot_compatibility() -> None:
    store = MemoryProcessStore()
    finalized = _snap(
        process_state=ProcessState.FINALIZED,
        finalized_by="insp-7",
        protocol_id="proto-1",
    )
    store.save(finalized)
    assert store.load("p-1") == finalized


def test_postgres_store_writes_non_final_snapshots_findings_and_audit() -> None:
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
    store.save_audit_event(
        "p-1", "insp-7", "REVIEW", {"action": "REJECT"}, object_id="obj-1"
    )
    assert any("INSERT INTO audit_log" in item for item in conn.sql)


def _finalized_snap() -> ProcessSnapshot:
    return _snap(
        process_state=ProcessState.FINALIZED,
        finalized_by="insp-7",
        protocol_id="protocol-p-1",
    )


def test_memory_materialize_is_idempotent_for_same_payload() -> None:
    store = MemoryProcessStore()
    payload = _final_payload()
    store.materialize_finalized(_finalized_snap(), payload)
    store.materialize_finalized(_finalized_snap(), payload)
    stored = store.load_protocol("protocol-p-1")
    assert stored is not None
    assert stored["version"] == 1
    assert store.next_protocol_version("obj-1") == 2
    assert store._outbox["protocol-p-1"]["status"] == "PENDING"


def test_memory_materialize_conflicts_on_different_payload() -> None:
    store = MemoryProcessStore()
    store.materialize_finalized(_finalized_snap(), _final_payload())
    with pytest.raises(ProtocolConflictError, match="другое содержимое"):
        store.materialize_finalized(
            _finalized_snap(), _final_payload(violation_count=1)
        )


def test_memory_materialize_conflicts_on_object_version() -> None:
    store = MemoryProcessStore()
    store.materialize_finalized(_finalized_snap(), _final_payload())
    other = _snap(
        process_id="p-2",
        process_state=ProcessState.FINALIZED,
        finalized_by="insp-7",
        protocol_id="protocol-p-2",
    )
    with pytest.raises(ProtocolConflictError, match="уже занята"):
        store.materialize_finalized(
            other, _final_payload(protocol_id="protocol-p-2")
        )


def test_memory_rejects_placeholder_payload() -> None:
    store = MemoryProcessStore()
    with pytest.raises(ProtocolMaterializationRequiredError, match="placeholder"):
        store.materialize_finalized(
            _snap(
                process_state=ProcessState.FINALIZED,
                finalized_by="insp-7",
                protocol_id="placeholder-p-1",
            ),
            _final_payload(protocol_id="placeholder-p-1"),
        )


def test_postgres_materialize_writes_protocol_and_process_in_transaction() -> None:
    conn = _Conn()
    store = PostgresProcessStore(conn)
    store.materialize_finalized(_finalized_snap(), _final_payload())
    joined = "\n".join(conn.sql)
    assert "INSERT INTO protocols" in joined
    assert "INSERT INTO processes" in joined
    assert "pg_advisory_xact_lock" in joined
    assert "FOR UPDATE" in joined
    assert "INSERT INTO integration_outbox" in joined
    assert "payload_sha256" in joined
    assert conn.saw_transaction is True
    assert conn.sql.index(
        [item for item in conn.sql if "INSERT INTO protocols" in item][0]
    ) < conn.sql.index(
        [item for item in conn.sql if "INSERT INTO processes" in item][0]
    )


def test_postgres_materialize_is_idempotent_for_same_canonical_json() -> None:
    conn = _Conn()
    conn.protocol_insert_rows = None
    payload = _final_payload()
    conn.existing_payload = payload
    store = PostgresProcessStore(conn)
    store.materialize_finalized(_finalized_snap(), payload)
    assert any("FOR UPDATE" in item for item in conn.sql)
    assert any("INSERT INTO processes" in item for item in conn.sql)


def test_postgres_materialize_conflicts_on_different_payload() -> None:
    conn = _Conn()
    conn.protocol_insert_rows = None
    conn.existing_payload = _final_payload(violation_count=3)
    store = PostgresProcessStore(conn)
    with pytest.raises(ProtocolConflictError, match="другое содержимое"):
        store.materialize_finalized(_finalized_snap(), _final_payload())


def test_postgres_materialize_maps_unique_violation() -> None:
    conn = _Conn()
    conn.raise_unique = True
    store = PostgresProcessStore(conn)
    with pytest.raises(ProtocolConflictError, match="UNIQUE"):
        store.materialize_finalized(_finalized_snap(), _final_payload())


def test_postgres_materialize_fails_closed_without_transaction() -> None:
    conn = _NoTxConn()
    store = PostgresProcessStore(conn)
    with pytest.raises(TransactionUnavailableError, match="transaction"):
        store.materialize_finalized(_finalized_snap(), _final_payload())
    assert conn.sql == []


def test_postgres_next_protocol_version_increments() -> None:
    conn = _Conn()
    conn.max_version = 4
    store = PostgresProcessStore(conn)
    assert store.next_protocol_version("obj-1") == 5
