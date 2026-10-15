"""npm audit gate: allowlist expiry and stale entries fail."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pytest

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


def test_valid_allowlist_has_no_schema_errors() -> None:
    assert gate.validate_allowlist({"GHSA-a": _entry("2027-01-14")}) == []


def test_missing_expires_is_a_clear_error() -> None:
    entry = {"projects": ["gateway"], "justification": "unreachable"}
    errors = gate.validate_allowlist({"GHSA-a": entry})
    assert errors == ["allowlist entry GHSA-a: 'expires' is required (YYYY-MM-DD)"]


def test_malformed_expires_is_a_clear_error() -> None:
    errors = gate.validate_allowlist({"GHSA-a": _entry("14.01.2027")})
    assert errors == ["allowlist entry GHSA-a: 'expires' '14.01.2027' is not YYYY-MM-DD"]


def test_main_exits_nonzero_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "npm_audit_allowlist.json"
    bad.write_text('{"GHSA-a": {"projects": ["gateway"], "justification": "x"}}', encoding="utf-8")
    monkeypatch.setattr(gate, "ALLOWLIST", bad)
    monkeypatch.setattr(sys, "argv", ["check_npm_audit.py", "gateway"])
    assert gate.main() == 2
    err = capsys.readouterr().err
    assert "'expires' is required" in err
    assert "Traceback" not in err
