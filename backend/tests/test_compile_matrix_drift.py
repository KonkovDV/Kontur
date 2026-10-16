"""Правила матрицы в git совпадают с результатом scripts/compile_matrix.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _compiler() -> ModuleType:
    script = ROOT / "scripts" / "compile_matrix.py"
    spec = importlib.util.spec_from_file_location("compile_matrix", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["compile_matrix"] = module
    spec.loader.exec_module(module)
    return module


def test_committed_rules_match_compiler_output() -> None:
    assert _compiler().check() == []


def test_hand_extractors_live_in_overrides() -> None:
    overrides = {path.stem for path in (ROOT / "data" / "matrix" / "overrides").glob("*.json")}
    for path in (ROOT / "data" / "matrix" / "rules").glob("*.json"):
        rule = json.loads(path.read_text(encoding="utf-8"))
        if rule["coverage"] == "executable":
            assert path.stem in overrides, path.stem


def test_check_reports_hand_edit(tmp_path: Path) -> None:
    compiler = _compiler()
    rules = tmp_path / "rules"
    rules.mkdir()
    for path in (ROOT / "data" / "matrix" / "rules").glob("*.json"):
        (rules / path.name).write_bytes(path.read_bytes())
    edited = rules / "AR-040.json"
    rule = json.loads(edited.read_text(encoding="utf-8"))
    rule["coverage"] = "extractor_missing"
    edited.write_text(json.dumps(rule, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compiler.RULES = rules
    assert compiler.check() == ["data/matrix/rules/AR-040.json"]
