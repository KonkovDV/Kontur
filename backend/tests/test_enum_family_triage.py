"""Девять оставшихся enum не становятся исполняемыми из названия параметра."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TRIAGE = REPO / "data" / "matrix" / "enum_family_triage.json"
RULES = REPO / "data" / "matrix" / "rules"


def _triage() -> dict[str, object]:
    return json.loads(TRIAGE.read_text(encoding="utf-8"))


def test_enum_triage_keeps_every_rule_missing() -> None:
    payload = _triage()
    assert payload["closes_gate_j"] is False
    assert payload["decision_counts"] == {
        "kept_extractor_missing": 9,
        "promoted_executable": 0,
    }
    entries = payload["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 9
    reasons = payload["reason_codes"]
    assert isinstance(reasons, dict)
    for entry in entries:
        assert isinstance(entry, dict)
        code = str(entry["code"])
        assert entry["decision"] == "kept_extractor_missing"
        assert entry["reason_code"] in reasons
        rule = json.loads((RULES / f"{code}.json").read_text(encoding="utf-8"))
        extractor = rule["extractor"]
        assert isinstance(extractor, dict)
        assert extractor["type"] == "enum"
        assert extractor["regex"] is None
        assert rule["coverage"] == "extractor_missing"
