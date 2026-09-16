"""Реестр правил: валидность по схеме, честное покрытие, обязательные фикстуры."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "rule.schema.json"


@pytest.fixture(scope="module")
def registry() -> FileRuleRegistry:
    return FileRuleRegistry(REPO_ROOT / "data" / "matrix")


def test_rules_load_with_single_matrix_version(registry: FileRuleRegistry) -> None:
    assert registry.all_codes()
    assert registry.matrix_version == "draft-0"


def test_every_rule_validates_against_schema(registry: FileRuleRegistry) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    for code in registry.all_codes():
        jsonschema.validate(registry.get(code), schema)


def test_every_rule_has_fixtures(registry: FileRuleRegistry) -> None:
    """Правило без фикстур не попадает в релиз (ADR-0004)."""

    for code in registry.all_codes():
        tests = registry.get(code).get("tests") or []
        assert isinstance(tests, list) and tests, f"{code}: нет фикстур"


def test_executable_rule_declares_comparator_and_evidence(registry: FileRuleRegistry) -> None:
    for code in registry.all_codes():
        rule = registry.get(code)
        if rule["coverage"] != "executable":
            continue
        assert rule["comparator"]["operator"]
        assert rule["required_evidence"]


def test_coverage_report_does_not_overclaim(registry: FileRuleRegistry) -> None:
    """Реестр не имеет права заявлять больше правил, чем в матрице."""

    report = registry.coverage_report()
    assert report["expected_total"] == EXPECTED_PARAM_COUNT
    assert report["declared"] <= EXPECTED_PARAM_COUNT
    assert report["executable"] <= report["declared"]


@pytest.mark.xfail(reason="Приложение 1 не передано организатором (вопрос 1)", strict=True)
def test_all_132_params_present(registry: FileRuleRegistry) -> None:
    assert len(registry.all_codes()) == EXPECTED_PARAM_COUNT
