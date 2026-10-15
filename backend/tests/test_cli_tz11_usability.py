"""CLI wrappers keep stdout output; diagnostics go through logging; library modules do not print."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from kontur.cli import tz11 as tz11_cli
from kontur.cli import usability_audit as ua_cli

SRC = Path(__file__).resolve().parents[1] / "src" / "kontur" / "evaluation"


@pytest.mark.parametrize("name", ["tz11.py", "usability_audit.py"])
def test_library_modules_do_not_print(name: str) -> None:
    assert "print(" not in (SRC / name).read_text(encoding="utf-8")


def test_usability_usage_error_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert ua_cli.main([]) == 2
    out = capsys.readouterr()
    assert out.out == ""


def test_tz11_missing_json_arg_returns_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert tz11_cli.main(["--from-json"]) == 2
    assert capsys.readouterr().out == ""


def test_module_entrypoint_still_works() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "kontur.evaluation.usability_audit"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "usage: python -m kontur.evaluation.usability_audit" in proc.stderr
    assert proc.stdout == ""


def test_tz11_from_json_writes_table_and_json(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    path.write_text("{}", encoding="utf-8")
    proc = subprocess.run(  # noqa: S603 — fixed argv, temp path from tmp_path
        [sys.executable, "-m", "kontur.evaluation.tz11", "--from-json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    last = proc.stdout.strip().splitlines()[-1]
    assert isinstance(json.loads(last), (dict, list))
