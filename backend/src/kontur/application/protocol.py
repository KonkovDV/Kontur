"""Черновик протокола п. 9.2. AUTO_NO_DIFFERENCE не выходит на провод ТЗ/РиН."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC

from kontur.application.scenarios import CompletenessMap, detect_scenario
from kontur.domain.models import DocStage, Finding
from kontur.domain.status_map import PROTOCOL_STATUS, on_the_wire, tz_upload_status
from kontur.domain.statuses import FindingStatus, ProcessState

_SECTION: dict[FindingStatus, str] = {
    FindingStatus.CANDIDATE: "candidates",
    FindingStatus.CONFIRMED_VIOLATION: "confirmed",
    FindingStatus.NEGATIVE_VERIFIED: "negative_verified",
    FindingStatus.SUSPICION: "suspicions",
    FindingStatus.MISSING_EVIDENCE: "missing_evidence",
    FindingStatus.AUTO_NO_DIFFERENCE: "preliminary_no_difference",
    FindingStatus.LOW_QUALITY: "needs_attention",
    FindingStatus.ABSTAIN: "needs_attention",
    FindingStatus.CLARIFICATION_REQUIRED: "needs_attention",
    FindingStatus.NOT_COMPARABLE: "needs_attention",
    FindingStatus.NOT_APPLICABLE: "needs_attention",
}


def protocol_identity(process_id: str, version: int) -> str:
    """Стабильный id версии: v1 без суффикса, дальше `-vN`."""

    if not process_id.strip():
        raise ValueError("process_id обязателен")
    if version < 1:
        raise ValueError("version должен быть >= 1")
    if version == 1:
        return f"protocol-{process_id}"
    return f"protocol-{process_id}-v{version}"


def canonical_protocol_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def reject_placeholder_payload(payload: Mapping[str, object]) -> None:
    """Запрет legacy placeholder до INSERT. Не путать с HTTP-схемой протокола."""

    if payload.get("kind") == "internal_placeholder":
        raise ValueError("internal_placeholder нельзя материализовать")
    if payload.get("assembled") is False:
        raise ValueError("assembled=false нельзя материализовать")
    protocol_id = payload.get("protocol_id")
    if not isinstance(protocol_id, str) or not protocol_id.strip():
        raise ValueError("protocol_id обязателен")
    if protocol_id.startswith("placeholder-"):
        raise ValueError("placeholder protocol_id запрещён")


def protocol_for_http(payload: Mapping[str, object]) -> dict[str, object]:
    """Копия для провода ТЗ: карман AUTO_NO_DIFFERENCE не сериализуется."""

    clone: dict[str, object] = json.loads(canonical_protocol_json(payload))
    sections = clone.get("sections")
    if isinstance(sections, dict):
        sections.pop("preliminary_no_difference", None)
    return clone


def finding_to_schema(finding: Finding) -> dict[str, object]:
    """Карточка по finding.schema.json. Лишних ключей нет: additionalProperties=false."""

    payload: dict[str, object] = {
        "finding_id": finding.finding_id,
        "rule_code": finding.rule_code,
        "finding_status": finding.finding_status.value,
        "review_priority": finding.review_priority.value,
        "counts_as_violation": finding.counts_as_violation,
        "rationale": finding.rationale,
        "versions": {
            "matrix_version": finding.matrix_version,
            "rule_version": finding.rule_version,
            "model_version": finding.model_version,
        },
    }
    if finding.evidence_group_id is not None:
        payload["evidence_group_id"] = finding.evidence_group_id
    if finding.expected_value is not None:
        payload["expected_value"] = finding.expected_value
    if finding.actual_value is not None:
        payload["actual_value"] = finding.actual_value
    if finding.delta is not None:
        payload["delta"] = finding.delta
    if finding.llm_draft is not None:
        payload["llm_draft"] = finding.llm_draft
    if finding.source_id is not None:
        payload["source_id"] = finding.source_id
    if finding.evidence_refs:
        payload["evidence_refs"] = list(finding.evidence_refs)
    if finding.disagreement_kind is not None:
        payload["disagreement_kind"] = finding.disagreement_kind.value
    decision = finding.inspector_decision
    if decision is not None:
        stamp = decision.timestamp
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(UTC).replace(tzinfo=None)
        body: dict[str, object] = {
            "inspector_id": decision.inspector_id,
            "action": decision.action,
            "timestamp": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "comment": decision.comment,
        }
        if decision.reason_code is not None:
            body["reason_code"] = decision.reason_code.value
        payload["inspector_decision"] = body
    return payload


def assemble_protocol(
    *,
    protocol_id: str,
    object_id: str,
    findings: Sequence[Finding],
    completeness: CompletenessMap,
    files: Sequence[dict[str, str]],
    versions: dict[str, str],
    process_state: ProcessState = ProcessState.READY,
    input_manifest_hash: str,
    version: int = 1,
) -> dict[str, object]:
    """Собрать протокол. Кандидаты не входят в violation_count.

    AUTO_NO_DIFFERENCE кладётся только в `preliminary_no_difference` и не
    сериализуется в РиН: `on_the_wire` для него ложен, пока нет ответа на вопрос 8.
    """

    status = PROTOCOL_STATUS.get(process_state)
    if status is None:
        raise ValueError(f"{process_state}: ещё нет протокола (PENDING/PARSING)")

    sections: dict[str, list[object]] = {
        "completeness": [],
        "candidates": [],
        "confirmed": [],
        "negative_verified": [],
        "suspicions": [],
        "missing_evidence": [],
        "needs_attention": [],
        "preliminary_no_difference": [],
    }
    for finding in findings:
        if finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE:
            if on_the_wire(finding.finding_status):
                raise RuntimeError("AUTO_NO_DIFFERENCE нельзя отдавать в РиН")
            sections["preliminary_no_difference"].append(finding_to_schema(finding))
            continue
        bucket = _SECTION.get(finding.finding_status)
        if bucket is None:
            raise ValueError(f"{finding.finding_status.value} не входит ни в одну секцию протокола")
        sections[bucket].append(finding_to_schema(finding))

    confirmed = sections["confirmed"]
    return {
        "protocol_id": protocol_id,
        "object_id": object_id,
        "version": version,
        "status": status,
        "scenario": detect_scenario(completeness).value,
        "upload_status": {
            "pd": tz_upload_status(DocStage.PD, completeness[DocStage.PD]),
            "rd": tz_upload_status(DocStage.RD, completeness[DocStage.RD]),
            "id": tz_upload_status(DocStage.ID, completeness[DocStage.ID]),
        },
        "sections": sections,
        "violation_count": len(confirmed),
        "versions": versions,
        "input_manifest": {
            "manifest_hash": input_manifest_hash,
            "files": list(files),
        },
    }
