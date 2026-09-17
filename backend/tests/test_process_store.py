"""DAO процессов: инварианты schema.sql без живого Postgres в pytest."""

from __future__ import annotations

import pytest

from kontur.application.runtime import ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness, ProcessState, Scenario, SyncState
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
