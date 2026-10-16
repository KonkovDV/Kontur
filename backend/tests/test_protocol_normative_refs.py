"""Протокол пишет normative_refs находки из JSON правила матрицы и ничего больше не меняет."""

from __future__ import annotations

import json
from pathlib import Path

from kontur.application.protocol import finding_to_schema, rule_normative_refs
from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus, ReviewPriority

ROOT = Path(__file__).resolve().parents[2]


def _finding(rule_code: str) -> Finding:
    return Finding(
        finding_id="f-1",
        rule_code=rule_code,
        finding_status=FindingStatus.MISSING_EVIDENCE,
        review_priority=ReviewPriority.MEDIUM,
        matrix_version="draft-0",
        rule_version="1",
        model_version="m",
    )


def _rule(code: str) -> dict[str, object]:
    data: dict[str, object] = json.loads(
        (ROOT / "data" / "matrix" / "rules" / f"{code}.json").read_text(encoding="utf-8")
    )
    return data


def test_refs_copied_from_rule_without_new_content() -> None:
    refs = rule_normative_refs("PZ-021")
    source = _rule("PZ-021")["normative_refs"]
    assert isinstance(source, list) and refs
    assert [ref["identifier"] for ref in refs] == [ref["identifier"] for ref in source]
    assert [ref["clause"] for ref in refs] == [ref["clause"] for ref in source]
    assert all("mandatory" not in ref for ref in refs)


def test_rule_without_refs_gets_none() -> None:
    codes = [p.stem for p in (ROOT / "data" / "matrix" / "rules").glob("*.json")]
    bare = next(code for code in sorted(codes) if not _rule(code).get("normative_refs"))
    assert rule_normative_refs(bare) == []
    assert "normative_refs" not in finding_to_schema(_finding(bare), rule_normative_refs(bare))
    assert rule_normative_refs("NO-SUCH-999") == []


def test_only_normative_refs_is_added() -> None:
    finding = _finding("PZ-021")
    before = finding_to_schema(finding)
    after = finding_to_schema(finding, rule_normative_refs("PZ-021"))
    assert set(after) - set(before) == {"normative_refs"}
    assert {key: after[key] for key in before} == before
