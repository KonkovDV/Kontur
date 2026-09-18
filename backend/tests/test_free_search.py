"""Tests for free-search loader and evaluator (FREE-HEATING-001 gold, Gate J)."""
from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from kontur.application.free_search_evaluator import evaluate_free_search
from kontur.infrastructure.matrix.free_search_loader import (
    FreeSearchRule,
    load_free_search_rules,
)


class _Page:
    def __init__(self, stage: str, text: str) -> None:
        self.stage = stage
        self.text = text


# ---------- loader tests ----------

def test_load_missing_file_returns_empty() -> None:
    result = load_free_search_rules(pathlib.Path("/nonexistent/free_search.json"))
    assert result == []


def test_load_valid_json_returns_rules() -> None:
    data = [
        {
            "id": "FREE-HEATING-001",
            "name": "Тёплые полы",
            "keywords": ["тёплый пол", "подогрев""],
            "stages": ["RD"],
            "normative_ref": "СП 41-102-98",
        }
    ]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        tmp_path = pathlib.Path(f.name)
    rules = load_free_search_rules(tmp_path)
    assert len(rules) == 1
    assert rules[0].id == "FREE-HEATING-001"
    assert "тёплый пол" in rules[0].keywords
    assert rules[0].stages == ["RD"]
    tmp_path.unlink()


def test_load_invalid_json_returns_empty() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        f.write("{invalid json}")
        tmp_path = pathlib.Path(f.name)
    result = load_free_search_rules(tmp_path)
    assert result == []
    tmp_path.unlink()


# ---------- evaluator tests ----------

def _make_rule(
    rule_id: str = "FREE-HEATING-001",
    keywords: list[str] | None = None,
    stages: list[str] | None = None,
) -> FreeSearchRule:
    return FreeSearchRule(
        id=rule_id,
        name="Test rule",
        keywords=keywords or ["тёплый пол"],
        stages=stages or ["RD"],
    )


def test_match_returns_finding() -> None:
    """FREE-HEATING-001: document mentions 'тёплый пол' → finding returned."""
    pages = [_Page("RD", "Предусмотрено устройство тёплый пол в санузлах")]
    rule = _make_rule()
    findings = evaluate_free_search(pages, [rule])
    assert len(findings) == 1
    assert findings[0]["parameter_code"] == "FREE-HEATING-001"
    assert findings[0]["is_free_search"] is True
    assert findings[0]["status"] == "FREE_SEARCH"


def test_no_match_returns_empty() -> None:
    pages = [_Page("RD", "Пластиковые окна в коллекторе 3 секции")]
    rule = _make_rule()
    findings = evaluate_free_search(pages, [rule])
    assert findings == []


def test_wrong_stage_not_matched() -> None:
    """Rule requires RD, page is PD → no match."""
    pages = [_Page("PD", "устройство тёплый пол в санузлах")]
    rule = _make_rule(stages=["RD"])
    findings = evaluate_free_search(pages, [rule])
    assert findings == []


def test_empty_rules_returns_empty() -> None:
    pages = [_Page("RD", "тёплый пол")]
    findings = evaluate_free_search(pages, [])
    assert findings == []


def test_evaluator_fail_open_on_bad_pages() -> None:
    """Evaluator must not raise on bad page objects (fail-open)."""
    bad_pages = [object(), None, 42]  # type: ignore[list-item]
    rule = _make_rule()
    # Should return empty, not raise
    findings = evaluate_free_search(bad_pages, [rule])  # type: ignore[arg-type]
    assert isinstance(findings, list)
