"""docs/FINDING_FIELDS.md matches the contract: present fields exist, listed gaps are real."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"


def _schema(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return data


def test_value_norm_and_place_fields_exist() -> None:
    finding = _schema("finding.schema.json")["properties"]
    for key in ("actual_value", "expected_value", "delta", "normative_refs", "evidence_group_id"):
        assert key in finding
    assert "clause" in finding["normative_refs"]["items"]["properties"]
    fragment = _schema("evidence_group.schema.json")["$defs"]["fragment"]["properties"]
    for key in ("document", "page", "polygon_source", "polygon_norm", "extracted"):
        assert key in fragment
    assert {"document", "page", "polygon_source", "polygon_norm"} <= set(
        _schema("evidence_group.schema.json")["$defs"]["fragment"]["required"]
    )
    extraction = _schema("evidence_group.schema.json")["$defs"]["extraction"]["properties"]
    assert "unit" in extraction


def test_documented_gaps_are_still_gaps() -> None:
    finding = _schema("finding.schema.json")
    assert "unit" not in finding["properties"]
    required = set(finding["required"])
    assert "normative_refs" not in required
    assert "evidence_group_id" not in required

    openapi = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
    get = openapi["paths"]["/processes/{process_id}/findings"]["get"]
    schema = get["responses"]["200"]["content"]["application/json"]["schema"]
    item = schema["properties"]["findings"]["items"]["properties"]
    for key in ("actual_value", "normative_refs", "page"):
        assert key not in item
