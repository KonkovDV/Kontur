"""Конкурсный вертикальный срез пяти правил. Не закрывает гейты I/J/K."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from kontur.domain.geometry import polygon_in_unit_square
from kontur.domain.models import EvidenceGroup, Finding
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, FindingStatus

CONTEST_SLICE_CODES: tuple[str, ...] = (
    "PZ-001",
    "KR-055",
    "AR-041",
    "IOS4-078",
    "IOS4-079",
)

HONEST_WITHOUT_FRAGMENTS: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.LOW_QUALITY,
        FindingStatus.ABSTAIN,
        FindingStatus.CLARIFICATION_REQUIRED,
        FindingStatus.MISSING_EVIDENCE,
        FindingStatus.NOT_APPLICABLE,
        FindingStatus.NOT_COMPARABLE,
    }
)


def contest_findings(findings: Sequence[Finding]) -> dict[str, Finding]:
    by_code = {item.rule_code: item for item in findings}
    missing = [code for code in CONTEST_SLICE_CODES if code not in by_code]
    if missing:
        raise KeyError(f"в отчёте нет правил среза: {missing}")
    return {code: by_code[code] for code in CONTEST_SLICE_CODES}


def groups_by_rule(groups: Sequence[EvidenceGroup]) -> dict[str, EvidenceGroup]:
    return {group.rule_code: group for group in groups}


def assert_contest_honest(
    finding: Finding,
    group: EvidenceGroup | None,
) -> None:
    """CANDIDATE с evidence или честный отказ. Автомат не пишет human-only."""

    if finding.finding_status in HUMAN_ONLY_STATUSES:
        raise AssertionError(f"{finding.rule_code}: автомат записал {finding.finding_status.value}")
    if finding.finding_status is FindingStatus.CONFIRMED_VIOLATION:
        raise AssertionError(f"{finding.rule_code}: CONFIRMED_VIOLATION без инспектора")
    if finding.finding_status in HONEST_WITHOUT_FRAGMENTS:
        if finding.evidence_group_id is not None:
            raise AssertionError(f"{finding.rule_code}: отказной статус с evidence_group_id")
        return
    if finding.finding_status not in {
        FindingStatus.CANDIDATE,
        FindingStatus.AUTO_NO_DIFFERENCE,
    }:
        raise AssertionError(
            f"{finding.rule_code}: неожиданный статус {finding.finding_status.value}"
        )
    if finding.evidence_group_id is None or group is None:
        raise AssertionError(f"{finding.rule_code}: предметный статус без evidence_group")
    if group.evidence_group_id != finding.evidence_group_id:
        raise AssertionError(f"{finding.rule_code}: group id расходится с находкой")
    if not group.fragments:
        raise AssertionError(f"{finding.rule_code}: пустые фрагменты")
    for fragment in group.fragments:
        if fragment.page < 1:
            raise AssertionError(f"{finding.rule_code}: страница < 1")
        if len(fragment.document.file_hash) != 64:
            raise AssertionError(f"{finding.rule_code}: нет SHA-256 источника")
        if not fragment.document.file_id.strip():
            raise AssertionError(f"{finding.rule_code}: нет file_id")
        if not polygon_in_unit_square(fragment.polygon_norm):
            raise AssertionError(f"{finding.rule_code}: polygon_norm вне [0;1]")


def contest_run_log(
    *,
    object_id: str,
    findings: Sequence[Finding],
    groups: Sequence[EvidenceGroup],
) -> list[dict[str, Any]]:
    """Запись прогона: object_id, file_id, SHA, статус. Не scorecard ТЗ."""

    grouped = groups_by_rule(groups)
    rows: list[dict[str, Any]] = []
    for code, finding in contest_findings(findings).items():
        group = grouped.get(code)
        assert_contest_honest(finding, group)
        row: dict[str, Any] = {
            "object_id": object_id,
            "rule_code": code,
            "finding_status": finding.finding_status.value,
            "evidence_group_id": finding.evidence_group_id,
            "source_id": finding.source_id,
            "closes_gate_j": False,
        }
        if group is not None:
            row["fragments"] = [
                {
                    "file_id": fragment.document.file_id,
                    "file_hash": fragment.document.file_hash,
                    "page": fragment.page,
                    "polygon_norm": [list(point) for point in fragment.polygon_norm],
                }
                for fragment in group.fragments
            ]
        rows.append(row)
    return rows


def contest_log_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["rule_code"]): row for row in rows}
