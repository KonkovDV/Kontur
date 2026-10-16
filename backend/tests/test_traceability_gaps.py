"""scripts/report_traceability_gaps.py считает пробелы и не валит CI."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    script = ROOT / "scripts" / "report_traceability_gaps.py"
    spec = importlib.util.spec_from_file_location("report_traceability_gaps", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["report_traceability_gaps"] = module
    spec.loader.exec_module(module)
    return module


def test_counts_match_repository() -> None:
    report = _module().collect()
    rules = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "data" / "matrix" / "rules").glob("*.json")
    ]
    assert report.rules_total == len(rules) == 132
    assert len(report.rules_without_refs) == sum(
        1 for rule in rules if not rule.get("normative_refs")
    )
    assert 0 <= report.findings_without_refs <= report.findings_total
    assert 0 <= report.findings_without_group <= report.findings_total


def test_counts_on_synthetic_input(tmp_path: Path) -> None:
    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "A-1.json").write_text(json.dumps({"normative_refs": [{"identifier": "x"}]}))
    (rules / "A-2.json").write_text(json.dumps({"normative_refs": []}))
    examples = tmp_path / "examples" / "one"
    examples.mkdir(parents=True)
    protocol = {
        "sections": {
            "candidates": [
                {
                    "finding_id": "f1",
                    "evidence_group_id": "g1",
                    "normative_refs": [{"identifier": "x"}],
                },
                {"finding_id": "f2"},
            ],
            "completeness": [{"section": "ПЗ"}],
        }
    }
    (examples / "protocol.json").write_text(json.dumps(protocol))
    report = _module().collect(rules, tmp_path / "examples")
    assert report.rules_without_refs == ("A-2",)
    assert (report.findings_total, report.findings_without_refs, report.findings_without_group) == (
        2,
        1,
        1,
    )


def test_warning_does_not_fail(capsys: pytest.CaptureFixture[str]) -> None:
    assert _module().main() == 0
    assert "::warning title=traceability::" in capsys.readouterr().out


def test_fields_are_not_required_before_demo() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "schemas" / "finding.schema.json").read_text(encoding="utf-8")
    )
    assert not {"normative_refs", "evidence_group_id"} & set(schema["required"])
    assert "normative_refs" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
