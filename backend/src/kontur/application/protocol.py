"""Черновик протокола п. 9.2. AUTO_NO_DIFFERENCE не выходит на провод ТЗ/РиН."""

from __future__ import annotations

from collections.abc import Sequence
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
}


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
            continue
        sections[bucket].append(finding_to_schema(finding))

    confirmed = sections["confirmed"]
    return {
        "protocol_id": protocol_id,
        "object_id": object_id,
        "version": 1,
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
