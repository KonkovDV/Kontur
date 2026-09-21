"""Карточка доказательства для инспектора. Не протокол ТЗ, не Gate K."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from kontur.application.protocol import finding_to_schema
from kontur.domain.models import (
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Extraction,
    Finding,
    Polygon,
)

SCHEMA_VERSION = "kontur.evidence_card.v1"


def polygon_to_schema(polygon: Polygon) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in polygon]


def document_ref_to_schema(ref: DocumentRef) -> dict[str, object]:
    payload: dict[str, object] = {
        "file_id": ref.file_id,
        "file_hash": ref.file_hash,
        "doc_stage": ref.doc_stage.value,
        "document_code": ref.document_code,
        "revision": ref.revision,
        "approval_status": ref.approval_status.value,
    }
    if ref.discipline is not None:
        payload["discipline"] = ref.discipline
    if ref.approval_date is not None:
        stamp: date = ref.approval_date
        payload["approval_date"] = stamp.isoformat()
    if ref.sheet is not None:
        payload["sheet"] = ref.sheet
    if ref.predecessor_file_id is not None:
        payload["predecessor_file_id"] = ref.predecessor_file_id
    if ref.successor_file_id is not None:
        payload["successor_file_id"] = ref.successor_file_id
    return payload


def extraction_to_schema(item: Extraction) -> dict[str, object]:
    payload: dict[str, object] = {
        "raw_token": item.raw_token,
        "engine": item.engine.value,
        "engine_version": item.engine_version,
        "confidence": item.confidence,
        "grounded_in_source_tokens": item.grounded_in_source_tokens,
    }
    if item.normalized_value is not None:
        payload["normalized_value"] = item.normalized_value
    if item.unit is not None:
        payload["unit"] = item.unit
    if item.second_read_agrees is not None:
        payload["second_read"] = {"agrees": item.second_read_agrees}
    if item.confidence_features:
        payload["confidence_features"] = dict(item.confidence_features)
    return payload


def fragment_to_schema(fragment: EvidenceFragment) -> dict[str, object]:
    return {
        "fragment_id": fragment.fragment_id,
        "role": fragment.role.value,
        "document": document_ref_to_schema(fragment.document),
        "page": fragment.page,
        "polygon_source": polygon_to_schema(fragment.polygon_source),
        "polygon_norm": polygon_to_schema(fragment.polygon_norm),
        "extracted": extraction_to_schema(fragment.extracted),
    }


def evidence_group_to_schema(group: EvidenceGroup) -> dict[str, object]:
    payload: dict[str, object] = {
        "evidence_group_id": group.evidence_group_id,
        "object_id": group.object_id,
        "rule_code": group.rule_code,
        "matrix_version": group.matrix_version,
        "fragments": [fragment_to_schema(item) for item in group.fragments],
    }
    if group.resolved_revisions:
        payload["resolved_revisions"] = [
            document_ref_to_schema(item) for item in group.resolved_revisions
        ]
    return payload


def rule_summary(rule: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {"code": str(rule.get("code", ""))}
    name = rule.get("name")
    if isinstance(name, str) and name:
        payload["name"] = name
    unit = rule.get("unit")
    if unit is None or isinstance(unit, str):
        if "unit" in rule:
            payload["unit"] = unit
    comparator = rule.get("comparator")
    if isinstance(comparator, dict):
        payload["comparator"] = {
            key: comparator[key]
            for key in (
                "operator",
                "tolerance_abs",
                "tolerance_rel",
                "rounding",
                "unit_target",
            )
            if key in comparator
        }
    return payload


def audit_for_finding(
    records: Sequence[tuple[str, str, dict[str, object]]],
    finding_id: str,
) -> list[dict[str, object]]:
    """События находки и смена эталона. Пустой список — честное отсутствие, не дыра."""

    events: list[dict[str, object]] = []
    for actor_id, action, payload in records:
        related = payload.get("finding_id")
        if related == finding_id or action == "SELECT_REVISION":
            events.append(
                {"actor_id": actor_id, "action": action, "payload": dict(payload)}
            )
    return events


def fragment_for_role(
    group: EvidenceGroup | None, role: EvidenceRole
) -> EvidenceFragment | None:
    if group is None:
        return None
    return group.role(role)


def build_evidence_card(
    *,
    process_id: str,
    finding: Finding,
    group: EvidenceGroup | None,
    rule: Mapping[str, object],
    audit_records: Sequence[tuple[str, str, dict[str, object]]],
) -> dict[str, Any]:
    """Собрать kontur.evidence_card.v1. Автомат не пишет CONFIRMED_VIOLATION."""

    if group is not None and finding.evidence_group_id not in (None, group.evidence_group_id):
        raise ValueError(
            f"{finding.finding_id}: evidence_group_id расходится с группой"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "process_id": process_id,
        "finding": finding_to_schema(finding),
        "evidence_group": None if group is None else evidence_group_to_schema(group),
        "rule": rule_summary(rule),
        "audit": audit_for_finding(audit_records, finding.finding_id),
        "closes_gate_k": False,
    }
