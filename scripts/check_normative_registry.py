#!/usr/bin/env python3
"""Normative registry check (docs/NORMATIVE_REGISTRY.md).

Errors (exit 1): schema violations, non-ISO or inverted dates, duplicate ids/identifiers, a rule
``normative_refs`` identifier missing from the registry.
Warnings: a rule reference whose issuer, ``effective_from`` or ``mandatory`` differs from the
registry (data drift to fix in the rule files), and entries not yet verified.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "normative" / "registry.yaml"
SCHEMA = ROOT / "contracts" / "schemas" / "normative_registry.schema.json"
RULES = ROOT / "data" / "matrix" / "rules"


def _date(value: Any) -> dt.date | None:
    if value is None:
        return None
    return dt.date.fromisoformat(str(value))


def check(
    registry: dict[str, Any], schema: dict[str, Any], rules: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for err in jsonschema.Draft202012Validator(schema).iter_errors(registry):
        errors.append(f"schema: {'/'.join(str(p) for p in err.absolute_path)}: {err.message}")
    if errors:
        return errors, warnings

    by_name: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    for act in registry["acts"]:
        if act["id"] in ids:
            errors.append(f"{act['id']}: duplicate id")
        ids.add(act["id"])
        for key in ("date", "effective_from", "effective_to"):
            try:
                _date(act.get(key))
            except ValueError:
                errors.append(f"{act['id']}: {key} {act.get(key)!r} is not YYYY-MM-DD")
        try:
            start, end = _date(act["effective_from"]), _date(act["effective_to"])
            if start and end and end < start:
                errors.append(f"{act['id']}: effective_to {end} is before effective_from {start}")
        except ValueError:
            pass
        for name in [act["identifier"], *act.get("aliases", [])]:
            if name in by_name:
                errors.append(
                    f"{act['id']}: identifier {name!r} already used by {by_name[name]['id']}"
                )
            by_name[name] = act

    for code, rule in sorted(rules.items()):
        for ref in rule.get("normative_refs", []):
            act = by_name.get(ref["identifier"])
            if act is None:
                errors.append(f"{code}: normative_refs {ref['identifier']!r} not in registry")
                continue
            for key in ("issuer", "effective_from", "mandatory"):
                if key in ref and ref[key] != act[key]:
                    warnings.append(
                        f"{code}: {ref['identifier']} {key}={ref[key]!r}, registry={act[key]!r}"
                    )
    unverified = sorted(a["id"] for a in registry["acts"] if not a["verified"])
    if unverified:
        warnings.append(
            f"{len(unverified)} acts not verified against the official publication: "
            + ", ".join(unverified)
        )
    return errors, warnings


def load_rules(path: Path = RULES) -> dict[str, dict[str, Any]]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.json"))}


def main() -> int:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors, warnings = check(registry, schema, load_rules())
    for line in warnings:
        print(f"::warning::normative: {line}")
    for line in errors:
        print(f"normative: {line}", file=sys.stderr)
    acts = registry.get("acts", []) if isinstance(registry, dict) else []
    print(f"normative: {len(acts)} acts, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
