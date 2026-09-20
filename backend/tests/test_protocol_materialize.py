"""Версионная материализация протокола: identity, карман ТЗ, workspace."""

from __future__ import annotations

import pytest

from kontur.application.protocol import (
    assemble_protocol,
    canonical_protocol_json,
    protocol_for_http,
    protocol_identity,
    reject_placeholder_payload,
)
from kontur.application.runtime import ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage, Finding
from kontur.domain.state_machines import Actor
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState, ReviewPriority
from kontur.infrastructure.db.process_store import MemoryProcessStore


def _completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def test_protocol_identity_stable_for_v1_and_suffix_after() -> None:
    assert protocol_identity("abc", 1) == "protocol-abc"
    assert protocol_identity("abc", 2) == "protocol-abc-v2"
    with pytest.raises(ValueError, match="version"):
        protocol_identity("abc", 0)


def test_canonical_json_is_order_independent() -> None:
    left = canonical_protocol_json({"b": 1, "a": {"z": 2, "y": 3}})
    right = canonical_protocol_json({"a": {"y": 3, "z": 2}, "b": 1})
    assert left == right


def test_reject_placeholder_payload() -> None:
    with pytest.raises(ValueError, match="internal_placeholder"):
        reject_placeholder_payload({"kind": "internal_placeholder", "protocol_id": "p"})
    with pytest.raises(ValueError, match="assembled=false"):
        reject_placeholder_payload({"assembled": False, "protocol_id": "p"})
    with pytest.raises(ValueError, match="placeholder"):
        reject_placeholder_payload({"protocol_id": "placeholder-x"})


def test_protocol_for_http_drops_auto_no_difference_pocket() -> None:
    payload = assemble_protocol(
        protocol_id="protocol-p-1",
        object_id="obj-1",
        findings=(
            Finding(
                finding_id="f-eq",
                evidence_group_id="eg-eq",
                rule_code="PZ-001",
                finding_status=FindingStatus.AUTO_NO_DIFFERENCE,
                review_priority=ReviewPriority.LOW,
                matrix_version="draft-0",
                rule_version="0.1.0",
                model_version="none",
            ),
        ),
        completeness=_completeness(),
        files=[],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        process_state=ProcessState.FINALIZED,
        input_manifest_hash="pending",
        version=1,
    )
    assert payload["sections"]["preliminary_no_difference"]
    wire = protocol_for_http(payload)
    assert "preliminary_no_difference" not in wire["sections"]
    assert "AUTO_NO_DIFFERENCE" not in canonical_protocol_json(wire)
    assert payload["sections"]["preliminary_no_difference"]


def test_workspace_finalize_assigns_protocol_prefix_and_stores_payload() -> None:
    store = MemoryProcessStore()
    workspace = ProcessWorkspace(store=store)
    record = workspace.create("obj-1", _completeness())
    record.process_state = ProcessState.COMPLETED
    updated = workspace.finalize(
        record.process_id, Actor(actor_id="insp-7", is_human=True)
    )
    assert updated.protocol_id == f"protocol-{record.process_id}"
    stored = store.load_protocol(updated.protocol_id or "")
    assert stored is not None
    assert stored["status"] == "PROTOCOL_FINALIZED"
    assert stored["version"] == 1
    assert stored["protocol_id"] == updated.protocol_id


def test_workspace_re_finalize_after_unfinalize_uses_next_version() -> None:
    store = MemoryProcessStore()
    workspace = ProcessWorkspace(store=store)
    record = workspace.create("obj-1", _completeness())
    record.process_state = ProcessState.COMPLETED
    inspector = Actor(actor_id="insp-7", is_human=True)
    first = workspace.finalize(record.process_id, inspector)
    first_id = first.protocol_id
    workspace.unfinalize(
        record.process_id,
        Actor(actor_id="sup-1", is_human=True, is_supervisor=True),
        "ошибочная финализация",
    )
    second = workspace.finalize(record.process_id, inspector)
    assert first_id == f"protocol-{record.process_id}"
    assert second.protocol_id == f"protocol-{record.process_id}-v2"
    v1 = store.load_protocol_version("obj-1", 1)
    v2 = store.load_protocol_version("obj-1", 2)
    assert v1 is not None and v1["version"] == 1
    assert v2 is not None and v2["version"] == 2
    assert v1["protocol_id"] != v2["protocol_id"]
