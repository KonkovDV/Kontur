#!/usr/bin/env python3
"""npm audit gate.

Production advisories fail the job unless listed in scripts/npm_audit_allowlist.json with a
justification. Dev-only advisories (build tooling, not shipped in images) are printed as
warnings so they stay visible without blocking.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

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


def main() -> int:
    allowed = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    status = 0
    for name in sys.argv[1:]:
        project = Path(name)
        prod = advisories(project, omit_dev=True)
        dev_only = advisories(project, omit_dev=False) - prod
        permitted = {gid for gid, entry in allowed.items() if name in entry["projects"]}
        for gid in sorted(prod & permitted):
            print(f"{name}: {gid} allowlisted: {allowed[gid]['justification']}")
        for gid in sorted(prod - permitted):
            print(f"{name}: {gid} production advisory NOT allowlisted", file=sys.stderr)
            status = 1
        for gid in sorted(permitted - prod):
            print(f"{name}: allowlist entry {gid} no longer reported; remove it", file=sys.stderr)
            status = 1
        for gid in sorted(dev_only):
            note = "build tooling, not in runtime images"
            print(f"::warning::{name}: dev-only advisory {gid} ({note})")
        if not prod and not dev_only:
            print(f"{name}: no advisories")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
