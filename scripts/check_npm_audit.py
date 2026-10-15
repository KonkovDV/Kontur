#!/usr/bin/env python3
"""npm audit gate.

Production advisories fail the job unless listed in scripts/npm_audit_allowlist.json with a
justification and an ``expires`` date. Expired entries and entries that are no longer reported
also fail. Dev-only advisories (build tooling, not shipped in images) are printed as warnings so
they stay visible without blocking.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

NPM = shutil.which("npm") or "npm"
ALLOWLIST = Path(__file__).with_name("npm_audit_allowlist.json")


def advisories(project: Path, *, omit_dev: bool) -> set[str]:
    cmd = [NPM, "audit", "--json"] + (["--omit=dev"] if omit_dev else [])
    out = subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, cwd=project, capture_output=True, text=True, check=False
    ).stdout
    found: set[str] = set()
    for vuln in json.loads(out).get("vulnerabilities", {}).values():
        for via in vuln.get("via", []):
            if isinstance(via, dict) and via.get("url"):
                found.add(via["url"].rsplit("/", 1)[-1])
    return found


def validate_allowlist(allowed: Any) -> list[str]:
    """Return schema errors for the allowlist; empty when every entry is well-formed."""
    if not isinstance(allowed, dict):
        return ["allowlist must be a JSON object keyed by advisory id"]
    errors: list[str] = []
    for gid, entry in sorted(allowed.items()):
        if not isinstance(entry, dict):
            errors.append(f"allowlist entry {gid}: must be an object")
            continue
        projects = entry.get("projects")
        if not isinstance(projects, list) or not all(isinstance(p, str) for p in projects):
            errors.append(f"allowlist entry {gid}: 'projects' must be a list of strings")
        justification = entry.get("justification")
        if not isinstance(justification, str) or not justification.strip():
            errors.append(f"allowlist entry {gid}: 'justification' is required")
        expires = entry.get("expires")
        if expires is None:
            errors.append(f"allowlist entry {gid}: 'expires' is required (YYYY-MM-DD)")
        else:
            try:
                dt.date.fromisoformat(str(expires))
            except ValueError:
                errors.append(f"allowlist entry {gid}: 'expires' {expires!r} is not YYYY-MM-DD")
    return errors


def evaluate(
    name: str,
    prod: set[str],
    dev_only: set[str],
    allowed: dict[str, Any],
    today: dt.date,
) -> tuple[int, list[str], list[str]]:
    """Return (status, info lines, error lines) for one npm project."""
    info: list[str] = []
    errors: list[str] = []
    permitted = {gid for gid, entry in allowed.items() if name in entry["projects"]}
    for gid in sorted(permitted):
        expires = dt.date.fromisoformat(allowed[gid]["expires"])
        if expires < today:
            errors.append(f"{name}: allowlist entry {gid} expired on {expires}; re-review it")
    for gid in sorted(prod & permitted):
        info.append(f"{name}: {gid} allowlisted: {allowed[gid]['justification']}")
    for gid in sorted(prod - permitted):
        errors.append(f"{name}: {gid} production advisory NOT allowlisted")
    for gid in sorted(permitted - prod):
        errors.append(f"{name}: allowlist entry {gid} no longer reported; remove it")
    for gid in sorted(dev_only):
        note = "build tooling, not in runtime images"
        info.append(f"::warning::{name}: dev-only advisory {gid} ({note})")
    if not prod and not dev_only:
        info.append(f"{name}: no advisories")
    return (1 if errors else 0), info, errors


def main() -> int:
    try:
        allowed = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{ALLOWLIST.name}: cannot read allowlist: {exc}", file=sys.stderr)
        return 2
    schema_errors = validate_allowlist(allowed)
    for line in schema_errors:
        print(f"{ALLOWLIST.name}: {line}", file=sys.stderr)
    if schema_errors:
        return 2
    today = dt.datetime.now(dt.UTC).date()
    status = 0
    for name in sys.argv[1:]:
        project = Path(name)
        prod = advisories(project, omit_dev=True)
        dev_only = advisories(project, omit_dev=False) - prod
        rc, info, errors = evaluate(name, prod, dev_only, allowed, today)
        for line in info:
            print(line)
        for line in errors:
            print(line, file=sys.stderr)
        status = status or rc
    return status


if __name__ == "__main__":
    raise SystemExit(main())
