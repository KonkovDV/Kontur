"""Версионная материализация протокола: identity, карман ТЗ, workspace."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from test_pz001 import _finding_schema, _validate_protocol

from kontur.application.protocol import (
    assemble_protocol,
    canonical_protocol_json,
    protocol_for_http,
    protocol_identity,
    reject_placeholder_payload,
)
from kontur.application.runtime import ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage, Finding, InspectorDecision
from kontur.domain.state_machines import Actor
from kontur.domain.statuses import (
    STATUSES_REQUIRING_EVIDENCE,
    Completeness,
    FindingStatus,
    ProcessState,
    ReasonCode,
    ReviewPriority,
)
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
    from kontur.infrastructure.db.process_store import protocol_payload_sha256

    assert protocol_payload_sha256({"b": 1, "a": 2}) == protocol_payload_sha256(
        {"a": 2, "b": 1}
    )


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
    assert "kind" not in payload
    assert "assembled" not in payload
    assert payload["version"] == 1


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


def test_tz_protocol_schema_forbids_kind_and_assembled() -> None:
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "protocol.schema.json")
        .read_text(encoding="utf-8")
    )
    assert schema.get("additionalProperties") is False
    properties = schema["properties"]
    assert "kind" not in properties
    assert "assembled" not in properties


def test_quality_statuses_stay_in_needs_attention() -> None:
    findings = tuple(
        Finding(
            finding_id=f"f-{status.value}",
            rule_code="PZ-001",
            finding_status=status,
            review_priority=ReviewPriority.LOW,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        )
        for status in (
            FindingStatus.LOW_QUALITY,
            FindingStatus.ABSTAIN,
            FindingStatus.CLARIFICATION_REQUIRED,
            FindingStatus.NOT_COMPARABLE,
            FindingStatus.NOT_APPLICABLE,
        )
    )
    payload = assemble_protocol(
        protocol_id="protocol-p-1",
        object_id="obj-1",
        findings=findings,
        completeness=_completeness(),
        files=[],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        input_manifest_hash="a" * 64,
    )
    section = payload["sections"]
    assert isinstance(section, dict)
    rows = section["needs_attention"]
    assert isinstance(rows, list)
    assert {item["finding_status"] for item in rows} == {
        "LOW_QUALITY",
        "ABSTAIN",
        "CLARIFICATION_REQUIRED",
        "NOT_COMPARABLE",
        "NOT_APPLICABLE",
    }
    wire = protocol_for_http(payload)
    wire_sections = wire["sections"]
    assert isinstance(wire_sections, dict)
    assert wire_sections["needs_attention"]
    assert payload["violation_count"] == 0


def test_export_tables_match_protocol_sections_except_the_pocket() -> None:
    from kontur.application.protocol_export import TABLES

    payload = assemble_protocol(
        protocol_id="protocol-p-1",
        object_id="obj-1",
        findings=(),
        completeness=_completeness(),
        files=[],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        input_manifest_hash="a" * 64,
    )
    wire = protocol_for_http(payload)
    sections = wire["sections"]
    assert isinstance(sections, dict)
    assert set(sections) == set(TABLES)
    assert "missing_evidence" in TABLES
    assert "preliminary_no_difference" not in sections


def test_protocol_with_every_finding_status_matches_schema() -> None:
    now = datetime(2026, 9, 26, tzinfo=UTC)
    findings: list[Finding] = []
    for index, status in enumerate(FindingStatus):
        decision = None
        if status is FindingStatus.CONFIRMED_VIOLATION:
            decision = InspectorDecision("insp-1", "CONFIRM", now, comment="подтверждаю")
        elif status is FindingStatus.NEGATIVE_VERIFIED:
            decision = InspectorDecision(
                "insp-1",
                "REJECT",
                now,
                reason_code=ReasonCode.OCR_ERROR,
                comment="ошибка чтения",
            )
        findings.append(
            Finding(
                finding_id=f"f-{index}",
                rule_code="PZ-001",
                finding_status=status,
                review_priority=ReviewPriority.MEDIUM,
                matrix_version="draft-0",
                rule_version="1",
                model_version="none",
                evidence_group_id="eg-1" if status in STATUSES_REQUIRING_EVIDENCE else None,
                rationale="проверка схемы",
                inspector_decision=decision,
            )
        )
    payload = assemble_protocol(
        protocol_id="protocol-p-1",
        object_id="obj-1",
        findings=findings,
        completeness=_completeness(),
        files=[],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        input_manifest_hash="a" * 64,
    )
    _validate_protocol(payload)
    schema = _finding_schema()
    seen: set[str] = set()
    sections = payload["sections"]
    assert isinstance(sections, dict)
    for rows in sections.values():
        assert isinstance(rows, list)
        for row in rows:
            if isinstance(row, dict) and "finding_status" in row:
                jsonschema.validate(row, schema)
                seen.add(str(row["finding_status"]))
    assert seen == {status.value for status in FindingStatus}
