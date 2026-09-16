"""Реестр правил: валидность по схеме, честное покрытие, обязательные фикстуры."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from kontur.domain.rule_codes import canonicalize_rule_code, display_alias
from kontur.infrastructure.matrix.registry import (
    EXPECTED_PARAM_COUNT,
    KNOWN_COVERAGE,
    FileRuleRegistry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "rule.schema.json"
PARAMS_CSV = REPO_ROOT / "data" / "matrix" / "params.template.csv"
CATALOG = REPO_ROOT / "data" / "matrix" / "source" / "parameter_catalog_132.jsonl"
FREE_SEARCH = REPO_ROOT / "data" / "matrix" / "free_search.json"


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
    """Реестр не имеет права заявлять больше правил, чем в матрице.

    executable == 0 не закрепляем: первое рабочее извлечение не должно красить CI.
    """

    report = registry.coverage_report()
    assert report["expected_total"] == EXPECTED_PARAM_COUNT
    assert report["declared"] <= EXPECTED_PARAM_COUNT
    assert report["executable"] <= report["declared"]
    coverage_sum = sum(report[name] for name in KNOWN_COVERAGE)
    assert coverage_sum == report["declared"]
    assert set(report) <= KNOWN_COVERAGE | {"declared", "expected_total"}


def test_all_132_params_present(registry: FileRuleRegistry) -> None:
    assert len(registry.all_codes()) == EXPECTED_PARAM_COUNT
    catalog = [
        json.loads(line)
        for line in CATALOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {str(row["parameter_code"]) for row in catalog} == set(registry.all_codes())


def test_canonical_codes_are_zero_padded(registry: FileRuleRegistry) -> None:
    for code in registry.all_codes():
        assert code == canonicalize_rule_code(code), code
        prefix, number = code.rsplit("-", 1)
        assert number.isdigit() and len(number) == 3, code
        assert registry.get(display_alias(code))["code"] == code
        assert prefix


def test_appendix2_short_aliases_resolve(registry: FileRuleRegistry) -> None:
    assert registry.get("PZ-01")["code"] == "PZ-001"
    assert registry.get("KR-55")["code"] == "KR-055"
    assert registry.get("AR-41")["code"] == "AR-041"
    with pytest.raises(KeyError):
        registry.get("AR-14")


def test_cyrillic_section_prefixes_resolve_to_catalog_codes(
    registry: FileRuleRegistry,
) -> None:
    assert registry.get("ПЗ-1")["code"] == "PZ-001"
    assert registry.get("СМ-132")["code"] == "SM-132"
    assert registry.get("ООС-98")["code"] == "OOS-098"
    assert registry.get("ЗУ-124")["code"] == "ZU-124"
    with pytest.raises(KeyError):
        registry.get("CM-132")


def test_params_csv_matches_catalog() -> None:
    catalog = [
        json.loads(line)
        for line in CATALOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with PARAMS_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["code"] for row in rows] == [str(item["parameter_code"]) for item in catalog]
    assert len(rows) == EXPECTED_PARAM_COUNT


def test_free_search_is_not_a_matrix_rule(registry: FileRuleRegistry) -> None:
    payload = json.loads(FREE_SEARCH.read_text(encoding="utf-8"))
    extra = {item["parameter_code"] for item in payload["entries"]}
    assert extra
    assert extra.isdisjoint(set(registry.all_codes()))
    with pytest.raises(KeyError):
        registry.get("FREE-HEATING-001")


def test_empty_matrix_is_an_error(tmp_path: Path) -> None:
    rules = tmp_path / "rules"
    rules.mkdir()
    with pytest.raises(FileNotFoundError, match="пуста"):
        FileRuleRegistry(tmp_path).all_codes()


def test_unknown_coverage_is_rejected(tmp_path: Path, registry: FileRuleRegistry) -> None:
    rules = tmp_path / "rules"
    rules.mkdir()
    sample = dict(registry.get("PZ-001"))
    sample["coverage"] = "почти_готово"
    (rules / "PZ-001.json").write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage"):
        FileRuleRegistry(tmp_path).all_codes()
