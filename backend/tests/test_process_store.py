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
    UPSERT_PROCESS_SQL,
    MemoryProcessStore,
    ProcessSnapshot,
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
    assert "ON CONFLICT (id) DO UPDATE" in UPSERT_PROCESS_SQL
    assert "INSERT INTO objects" in ENSURE_OBJECT_SQL
    assert "PROTOCOL_FINALIZED" in PLACEHOLDER_PROTOCOL_SQL
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
    assert loaded.completeness[DocStage.PD] is Completeness.MISSING


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
