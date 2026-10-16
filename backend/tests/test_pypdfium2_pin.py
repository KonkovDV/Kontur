"""pypdfium2 закреплён точно и одинаково в pyproject и requirements.lock (до демо 30.10)."""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import version
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _pinned() -> str:
    deps = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    found = [d for d in deps["dependencies"] if d.startswith("pypdfium2")]
    assert len(found) == 1 and found[0].startswith("pypdfium2=="), found
    return found[0].split("==", 1)[1]


def test_pyproject_pin_matches_lock() -> None:
    lock = (BACKEND / "requirements.lock").read_text(encoding="utf-8")
    match = re.search(r"^pypdfium2==(\S+)", lock, re.MULTILINE)
    assert match is not None
    assert match.group(1) == _pinned()


def test_installed_pypdfium2_is_the_pinned_one() -> None:
    assert version("pypdfium2") == _pinned()
