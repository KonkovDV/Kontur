"""Process persistence and finalized-protocol atomicity."""

from __future__ import annotations

from contextlib import contextmanager
import json

import pytest

from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness, ProcessState, Scenario, SyncState
from kontur.infrastructure.db.process_store import (
    INSERT_PROTOCOL_SQL,
    SELECT_PROTOCOL_SQL,
    UPSERT_PROCESS_SQL,
    FileRecord,
    MemoryProcessStore,
    PostgresProcessStore,
    ProcessSnapshot,
    ProtocolConflictError,
    TransactionUnavailableError,
    protocol_id_for,
    snapshot_params,
    validate_snapshot,
)


def _snap(**overrides: object) -> ProcessSnapshot:
    values: dict[str, object] = {
        "process_id": "p-1", "object_id": "obj-1",
        "process_state": ProcessState.PARSING, "scenario": Scenario.SINGLE_ONLY,
        "matrix_version": "draft-0", "model_version": "none", "dataset_version": "data-1",
        "completeness_pd": Completeness.UPLOADED, "input_manifest_hash": "a" * 64,
        "files": (FileRecord("file-1", "b" * 64, "pz.pdf", DocStage.PD, 12),),
    }
    values.update(overrides)
    return ProcessSnapshot(**values)  # type: ignore[arg-type]


def _final(**overrides: object) -> ProcessSnapshot:
    values: dict[str, object] = {"process_state": ProcessState.FINALIZED,
        "finalized_by": "insp-7", "protocol_id": "placeholder-p-1"}
    values.update(overrides)
    return _snap(**values)


class _Cursor:
    def __init__(self, rows: list[object] | None = None) -> None: self.rows = rows or []
    def fetchone(self) -> object | None: return self.rows[0] if self.rows else None
    def fetchall(self) -> list[object]: return list(self.rows)


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.protocol: tuple[object, ...] | None = None
        self.protocol_payload: dict[str, object] | None = None
        self.in_transaction = False; self.commits = 0; self.rollbacks = 0
        self.fail_process = False

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        self.in_transaction = True
        before, before_payload = self.protocol, self.protocol_payload
        try: yield
        except Exception:
            self.protocol, self.protocol_payload = before, before_payload
            self.rollbacks += 1
            raise
        else: self.commits += 1
        finally: self.in_transaction = False

    def execute(self, sql: str, params: object = None) -> _Cursor:
        values = dict(params or {})  # type: ignore[arg-type]
        self.calls.append((sql, values))
        compact = " ".join(sql.split()).lower()
        if "from process_findings" in compact: return _Cursor()
        if "from protocols" in compact: return _Cursor([] if self.protocol is None else [self.protocol])
        if compact.startswith("insert into protocols"):
            assert self.in_transaction
            payload = json.loads(str(values["payload"]))
            self.protocol_payload = payload
            self.protocol = (values["object_id"], 1, values["matrix_version"], values["dataset_version"],
                values["model_version"], values["input_manifest_hash"], "PROTOCOL_FINALIZED", payload)
        if compact.startswith("insert into processes"):
            assert self.in_transaction
            if self.fail_process: raise RuntimeError("process transition failed")
        return _Cursor()


def _insert_params(conn: _Connection) -> dict[str, object]:
    return next(params for sql, params in conn.calls if sql == INSERT_PROTOCOL_SQL)


def test_memory_store_behavior_remains_backward_compatible() -> None:
    store = MemoryProcessStore(); snapshot = _snap(); store.save(snapshot)
    assert store.load("p-1") == snapshot


def test_finalized_snapshot_requires_human_and_protocol_reference() -> None:
    with pytest.raises(ValueError, match="finalized_by"):
        validate_snapshot(_snap(process_state=ProcessState.FINALIZED, protocol_id="p"))
    with pytest.raises(ValueError, match="protocol_id"):
        validate_snapshot(_snap(process_state=ProcessState.FINALIZED, finalized_by="insp-7"))


def test_final_protocol_id_is_stable_and_process_uses_actual_id() -> None:
    conn = _Connection(); PostgresProcessStore(conn).save(_final())
    inserted = _insert_params(conn)
    process = next(params for sql, params in conn.calls if sql == UPSERT_PROCESS_SQL)
    assert inserted["protocol_id"] == protocol_id_for("p-1")
    assert process["protocol_id"] == inserted["protocol_id"]
    assert "placeholder" not in str(inserted["protocol_id"])


def test_finalization_persists_complete_canonical_assembled_payload() -> None:
    conn = _Connection(); PostgresProcessStore(conn).save(_final())
    payload = conn.protocol_payload; assert payload is not None
    assert payload["protocol_id"] == protocol_id_for("p-1")
    assert payload["object_id"] == "obj-1" and payload["status"] == "PROTOCOL_FINALIZED"
    assert payload["scenario"] == "SINGLE_ONLY"
    assert payload["upload_status"]["pd"] == "PD_UPLOADED"  # type: ignore[index]
    assert payload["input_manifest"] == {"manifest_hash": "a" * 64,
        "files": [{"file_id": "file-1", "file_hash": "b" * 64}]}
    assert payload["versions"] == {"matrix_version": "draft-0", "model_version": "none",
        "dataset_version": "data-1"}
    encoded = _insert_params(conn)["payload"]
    assert encoded == json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert "internal_placeholder" not in str(encoded) and '"assembled":false' not in str(encoded)


def test_identical_retry_is_idempotent_after_full_content_comparison() -> None:
    conn = _Connection(); store = PostgresProcessStore(conn)
    store.save(_final()); count = sum(sql == INSERT_PROTOCOL_SQL for sql, _ in conn.calls)
    store.save(_final())
    assert sum(sql == INSERT_PROTOCOL_SQL for sql, _ in conn.calls) == count
    assert sum(sql == SELECT_PROTOCOL_SQL for sql, _ in conn.calls) == 2


def test_mismatched_existing_protocol_raises_typed_conflict() -> None:
    conn = _Connection(); store = PostgresProcessStore(conn); store.save(_final())
    assert conn.protocol is not None
    cells = list(conn.protocol); changed = dict(cells[7])  # type: ignore[arg-type]
    changed["violation_count"] = 99; cells[7] = changed; conn.protocol = tuple(cells)
    with pytest.raises(ProtocolConflictError): store.save(_final())
    assert conn.rollbacks == 1


def test_protocol_insert_and_process_transition_share_transaction_and_rollback() -> None:
    conn = _Connection(); conn.fail_process = True
    with pytest.raises(RuntimeError, match="transition"): PostgresProcessStore(conn).save(_final())
    assert conn.protocol is None and conn.rollbacks == 1
    protocol_call = next(i for i, (sql, _) in enumerate(conn.calls) if sql == INSERT_PROTOCOL_SQL)
    process_call = next(i for i, (sql, _) in enumerate(conn.calls) if sql == UPSERT_PROCESS_SQL)
    assert protocol_call < process_call


def test_finalization_fails_closed_without_transaction_api() -> None:
    class NoTransaction:
        def execute(self, sql: str, params: object = None) -> _Cursor:
            raise AssertionError("must fail before executing")
    with pytest.raises(TransactionUnavailableError): PostgresProcessStore(NoTransaction()).save(_final())


def test_sync_guard_rejects_legacy_placeholder_as_content_conflict() -> None:
    conn = _Connection(); conn.protocol = ("obj-1", 1, "draft-0", "data-1", "none", "a" * 64,
        "PROTOCOL_FINALIZED", {"kind": "internal_placeholder", "assembled": False})
    with pytest.raises(ProtocolConflictError):
        PostgresProcessStore(conn).save(_final(sync_state=SyncState.PENDING_SYNC))


def test_sql_has_no_blind_protocol_conflict_or_placeholder_payload() -> None:
    source = INSERT_PROTOCOL_SQL + SELECT_PROTOCOL_SQL
    assert "ON CONFLICT" not in INSERT_PROTOCOL_SQL and "FOR UPDATE" in SELECT_PROTOCOL_SQL
    assert "internal_placeholder" not in source and "assembled" not in source
    assert "payload" not in snapshot_params(_final())
