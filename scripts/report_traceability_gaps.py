"""Предупреждение (не ошибка): правила и находки без normative_refs / evidence_group_id.

После демо 30.10 поля станут обязательными (docs/FINDING_FIELDS.md, CHANGELOG.md).
До того скрипт только считает и печатает ::warning:: для GitHub Actions; код выхода 0.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "data" / "matrix" / "rules"
EXAMPLES = ROOT / "submission" / "05-additional" / "examples"


@dataclass(frozen=True)
class GapReport:
    rules_total: int
    rules_without_refs: tuple[str, ...]
    findings_total: int
    findings_without_refs: int
    findings_without_group: int


def _findings(protocol: object) -> Iterator[dict[str, object]]:
    if not isinstance(protocol, dict):
        return
    sections = protocol.get("sections")
    if not isinstance(sections, dict):
        return
    for rows in sections.values():
        if isinstance(rows, list):
            yield from (row for row in rows if isinstance(row, dict) and "finding_id" in row)


def collect(rules_dir: Path = RULES, examples_dir: Path = EXAMPLES) -> GapReport:
    missing: list[str] = []
    total = 0
    for path in sorted(rules_dir.glob("*.json")):
        total += 1
        rule = json.loads(path.read_text(encoding="utf-8"))
        if not rule.get("normative_refs"):
            missing.append(path.stem)
    findings = [
        row
        for path in sorted(examples_dir.rglob("protocol.json"))
        for row in _findings(json.loads(path.read_text(encoding="utf-8")))
    ]
    return GapReport(
        rules_total=total,
        rules_without_refs=tuple(missing),
        findings_total=len(findings),
        findings_without_refs=sum(1 for row in findings if not row.get("normative_refs")),
        findings_without_group=sum(1 for row in findings if not row.get("evidence_group_id")),
    )


def main() -> int:
    report = collect()
    lines = [
        f"правила без normative_refs: {len(report.rules_without_refs)} из {report.rules_total}",
        f"находки в примерах без normative_refs: {report.findings_without_refs} "
        f"из {report.findings_total}",
        f"находки в примерах без evidence_group_id: {report.findings_without_group} "
        f"из {report.findings_total}",
    ]
    for line in lines:
        print(f"::warning title=traceability::{line}")
    print("traceability: только предупреждение до демо 30.10, см. docs/FINDING_FIELDS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
