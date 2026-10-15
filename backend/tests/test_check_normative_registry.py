"""Normative registry check: schema, dates and rule references."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_normative_registry as reg  # noqa: E402

SCHEMA = json.loads(reg.SCHEMA.read_text(encoding="utf-8"))


def _registry() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(reg.REGISTRY.read_text(encoding="utf-8"))
    return data


def test_repository_registry_has_no_errors() -> None:
    errors, _ = reg.check(_registry(), SCHEMA, reg.load_rules())
    assert errors == []


def test_unknown_rule_reference_is_an_error() -> None:
    rules = {"X-001": {"normative_refs": [{"identifier": "СП 0.0000.0000"}]}}
    errors, _ = reg.check(_registry(), SCHEMA, rules)
    assert errors == ["X-001: normative_refs 'СП 0.0000.0000' not in registry"]


def test_malformed_date_is_an_error() -> None:
    data = copy.deepcopy(_registry())
    data["acts"][0]["effective_from"] = "10.01.2005"
    errors, _ = reg.check(data, SCHEMA, {})
    assert any("is not YYYY-MM-DD" in e for e in errors)


def test_inverted_dates_are_an_error() -> None:
    data = copy.deepcopy(_registry())
    data["acts"][0]["effective_from"] = "2020-01-01"
    data["acts"][0]["effective_to"] = "2019-01-01"
    errors, _ = reg.check(data, SCHEMA, {})
    assert any("before effective_from" in e for e in errors)


def test_unquoted_yaml_date_fails_schema() -> None:
    data = copy.deepcopy(_registry())
    data["acts"][0]["effective_from"] = yaml.safe_load("d: 2005-01-10")["d"]
    errors, _ = reg.check(data, SCHEMA, {})
    assert any(e.startswith("schema:") for e in errors)


def test_drift_is_a_warning_not_an_error() -> None:
    act = _registry()["acts"][0]
    rules = {
        "X-002": {
            "normative_refs": [{"identifier": act["identifier"], "effective_from": "1900-01-01"}]
        }
    }
    errors, warnings = reg.check(_registry(), SCHEMA, rules)
    assert errors == []
    assert any("X-002" in w and "effective_from" in w for w in warnings)
