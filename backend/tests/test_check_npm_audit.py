"""npm audit gate: allowlist expiry and stale entries fail."""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_npm_audit.py"
_SPEC = importlib.util.spec_from_file_location("check_npm_audit", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)

TODAY = dt.date(2026, 10, 16)


def _entry(expires: str) -> dict[str, object]:
    return {"projects": ["gateway"], "justification": "unreachable", "expires": expires}


def test_allowlisted_and_valid_passes() -> None:
    rc, _, errors = gate.evaluate(
        "gateway", {"GHSA-a"}, set(), {"GHSA-a": _entry("2027-01-14")}, TODAY
    )
    assert rc == 0
    assert errors == []


def test_expired_entry_fails() -> None:
    rc, _, errors = gate.evaluate(
        "gateway", {"GHSA-a"}, set(), {"GHSA-a": _entry("2026-10-15")}, TODAY
    )
    assert rc == 1
    assert any("expired" in e for e in errors)


def test_entry_no_longer_reported_fails() -> None:
    rc, _, errors = gate.evaluate("gateway", set(), set(), {"GHSA-a": _entry("2027-01-14")}, TODAY)
    assert rc == 1
    assert any("no longer reported" in e for e in errors)


def test_unlisted_production_advisory_fails() -> None:
    rc, _, errors = gate.evaluate("gateway", {"GHSA-b"}, set(), {}, TODAY)
    assert rc == 1
    assert any("NOT allowlisted" in e for e in errors)


def test_dev_only_advisory_warns_without_failing() -> None:
    rc, info, errors = gate.evaluate("web", set(), {"GHSA-c"}, {}, TODAY)
    assert rc == 0
    assert errors == []
    assert any(line.startswith("::warning::") for line in info)
