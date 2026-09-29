"""Триаж семейств exact_field/presence: решение принято по каждому правилу отдельно.

`data/matrix/family_triage.json` фиксирует, какой вид доказательства реально нужен
каждому из 28 правил этих семейств. Тесты держат триаж согласованным со
скомпилированной матрицей и запрещают объявлять графический признак текстовым
только потому, что подпись совпала с названием параметра.

Файл не объявляет покрытие 132/132 и не закрывает Gate J.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_ROOT = REPO_ROOT / "data" / "matrix"
RULES_DIR = MATRIX_ROOT / "rules"
TRIAGE_PATH = MATRIX_ROOT / "family_triage.json"
SNAPSHOT_PATH = MATRIX_ROOT / "coverage_snapshot.json"

#: Семейства, по которым слайс обязан иметь поштучное решение.
TRIAGED_FAMILIES = frozenset({"exact_field", "presence"})

DECISION_TO_COVERAGE = {
    "promoted_executable": "executable",
    "advisory": "advisory",
    "source_missing": "source_missing",
    "kept_extractor_missing": "extractor_missing",
}

#: Виды доказательства, по которым совпадение подписи в тексте ничего не доказывает.
NON_TEXTUAL_EVIDENCE = frozenset(
    {"graphic", "spatial_count", "mixed", "external_registry"}
)

#: extractor.type из contracts/schemas/rule.schema.json.
EXTRACTOR_TYPES = frozenset(
    {
        "exact_field",
        "number",
        "enum",
        "set",
        "presence",
        "geometry",
        "semantic_candidate",
    }
)


@pytest.fixture(scope="module")
def rules() -> dict[str, dict[str, object]]:
    found = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(RULES_DIR.glob("*.json"))
    }
    assert len(found) == 132
    return found


@pytest.fixture(scope="module")
def triage() -> dict[str, object]:
    return json.loads(TRIAGE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(triage: dict[str, object]) -> dict[str, dict[str, object]]:
    items = triage["entries"]
    assert isinstance(items, list) and items
    by_code = {str(item["code"]): item for item in items}
    assert len(by_code) == len(items), "дубликат кода в триаже"
    return by_code


def _family(rule: dict[str, object]) -> str:
    extractor = rule.get("extractor")
    if isinstance(extractor, dict) and extractor.get("type") is not None:
        return str(extractor["type"])
    return "unknown"


def _statuses(rule: dict[str, object]) -> set[str]:
    fixtures = rule.get("tests") or []
    assert isinstance(fixtures, list)
    return {str(item["expected_status"]) for item in fixtures}


def test_triage_covers_exactly_the_two_families(
    rules: dict[str, dict[str, object]], entries: dict[str, dict[str, object]]
) -> None:
    expected = {code for code, rule in rules.items() if _family(rule) in TRIAGED_FAMILIES}
    assert set(entries) == expected
    assert len(expected) == 28


def test_declared_family_and_coverage_match_the_matrix(
    rules: dict[str, dict[str, object]], entries: dict[str, dict[str, object]]
) -> None:
    for code, item in entries.items():
        rule = rules[code]
        assert item["declared_family"] == _family(rule), code
        decision = str(item["decision"])
        assert decision in DECISION_TO_COVERAGE, code
        assert item["coverage"] == DECISION_TO_COVERAGE[decision], code
        assert rule["coverage"] == item["coverage"], code


def test_every_entry_names_a_target_and_a_reason(
    entries: dict[str, dict[str, object]], triage: dict[str, object]
) -> None:
    kinds = triage["evidence_kinds"]
    assert isinstance(kinds, dict)
    for code, item in entries.items():
        assert str(item["evidence_kind"]) in kinds, code
        assert str(item["target_extractor"]) in EXTRACTOR_TYPES, code
        assert len(str(item["reason"])) >= 80, code


def test_non_textual_evidence_is_never_declared_executable(
    rules: dict[str, dict[str, object]], entries: dict[str, dict[str, object]]
) -> None:
    """Графика, подсчёт и внешние реестры не становятся executable по совпадению подписи."""

    non_textual = [
        code
        for code, item in entries.items()
        if str(item["evidence_kind"]) in NON_TEXTUAL_EVIDENCE
    ]
    assert len(non_textual) >= 20
    for code in non_textual:
        assert entries[code]["decision"] != "promoted_executable", code
        assert rules[code]["coverage"] != "executable", code


def test_promoted_rules_carry_a_real_extractor_and_fixtures(
    rules: dict[str, dict[str, object]], entries: dict[str, dict[str, object]]
) -> None:
    promoted = [
        code for code, item in entries.items() if item["decision"] == "promoted_executable"
    ]
    assert promoted
    for code in promoted:
        rule = rules[code]
        assert entries[code]["evidence_kind"] == "text_closed_vocabulary", code
        extractor = rule["extractor"]
        assert isinstance(extractor, dict)
        pattern = extractor.get("regex")
        assert isinstance(pattern, str) and pattern, code
        assert extractor.get("anchors"), code
        comparator = rule["comparator"]
        assert isinstance(comparator, dict)
        assert comparator["operator"] in {"eq", "ne"}, code
        assert _statuses(rule) >= {
            "AUTO_NO_DIFFERENCE",
            "CANDIDATE",
            "MISSING_EVIDENCE",
            "LOW_QUALITY",
        }, code


def test_advisory_and_source_missing_never_promise_a_candidate(
    rules: dict[str, dict[str, object]], entries: dict[str, dict[str, object]]
) -> None:
    incomplete = [
        code
        for code, item in entries.items()
        if item["coverage"] in {"advisory", "source_missing"}
    ]
    assert incomplete
    for code in incomplete:
        assert "CANDIDATE" not in _statuses(rules[code]), code
        applicability = rules[code]["applicability"]
        assert isinstance(applicability, dict), code
        condition = applicability["condition"]
        assert isinstance(condition, str) and condition, code


def test_source_missing_points_at_an_external_registry(
    rules: dict[str, dict[str, object]], entries: dict[str, dict[str, object]]
) -> None:
    for code, item in entries.items():
        if item["coverage"] != "source_missing":
            continue
        assert item["evidence_kind"] == "external_registry", code
        extractor = rules[code]["extractor"]
        assert isinstance(extractor, dict)
        assert extractor.get("regex") is None, code


def test_decision_counts_match_the_entries(
    triage: dict[str, object], entries: dict[str, dict[str, object]]
) -> None:
    counted = Counter(str(item["decision"]) for item in entries.values())
    assert triage["decision_counts"] == dict(sorted(counted.items()))
    assert triage["closes_gate_j"] is False


def test_triage_agrees_with_the_coverage_snapshot(
    entries: dict[str, dict[str, object]]
) -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    codes = snapshot["codes"]
    counts = snapshot["counts"]
    for code, item in entries.items():
        assert code in codes[str(item["coverage"])], code
    for bucket in ("advisory", "source_missing", "executable"):
        declared = sum(1 for item in entries.values() if item["coverage"] == bucket)
        assert counts[bucket] >= declared
    assert snapshot["executable_equals_declared"] is False
