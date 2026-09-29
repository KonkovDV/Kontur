"""Инварианты триажа числового семейства (data/matrix/number_family_triage.json).

Выборка должна воспроизводиться из матрицы, решения — быть полными,
согласованными с `coverage` и не пересекаться с предыдущими триажами.
"""

from __future__ import annotations

import json
from pathlib import Path

from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
MATRIX = REPO / "data" / "matrix"
TRIAGE = MATRIX / "number_family_triage.json"
EARLIER = (MATRIX / "family_triage.json", MATRIX / "class_ladder_triage.json")

_REGISTRY = FileRuleRegistry(MATRIX)

PROMOTED = ("ZU-125", "ZU-127", "ZU-128", "ZU-131", "SM-132", "PPM-114")


def _triage() -> dict[str, object]:
    return json.loads(TRIAGE.read_text(encoding="utf-8"))


def _entries() -> list[dict[str, object]]:
    entries = _triage()["entries"]
    assert isinstance(entries, list)
    return entries


def _earlier_codes() -> set[str]:
    out: set[str] = set()
    for path in EARLIER:
        for entry in json.loads(path.read_text(encoding="utf-8"))["entries"]:
            out.add(str(entry["code"]))
    return out


def test_triage_file_exists() -> None:
    assert TRIAGE.is_file()
    assert isinstance(_triage(), dict)


def test_triage_does_not_overlap_earlier_triages() -> None:
    codes = {str(e["code"]) for e in _entries()}
    assert codes.isdisjoint(_earlier_codes())


def test_triage_covers_every_remaining_number_rule() -> None:
    """Выборка воспроизводима: ни одно number-правило не забыто."""
    earlier = _earlier_codes()
    expected: set[str] = set()
    for code in _REGISTRY.all_codes():
        if code in earlier:
            continue
        rule = _REGISTRY.get(code)
        if rule["extractor"]["type"] != "number":
            continue
        if rule["coverage"] == "extractor_missing" or code in PROMOTED:
            expected.add(code)
    assert {str(e["code"]) for e in _entries()} == expected


def test_decision_counts_match_entries() -> None:
    triage = _triage()
    actual: dict[str, int] = {}
    for entry in _entries():
        key = str(entry["decision"])
        actual[key] = actual.get(key, 0) + 1
    assert triage["decision_counts"] == actual
    assert triage["total_surveyed"] == len(_entries())


def test_triage_does_not_claim_gate_j() -> None:
    triage = _triage()
    assert triage["closes_gate_j"] is False
    assert "132/132" in str(triage["note"])


def test_every_kept_rule_has_a_known_reason_code() -> None:
    known = _triage()["reason_codes"]
    assert isinstance(known, dict) and known
    for entry in _entries():
        if entry["decision"] != "kept_extractor_missing":
            continue
        assert str(entry["reason_code"]) in known, entry["code"]
        assert str(entry["rationale"]).strip(), entry["code"]


def test_decision_agrees_with_coverage_in_matrix() -> None:
    for entry in _entries():
        code = str(entry["code"])
        coverage = _REGISTRY.get(code)["coverage"]
        if entry["decision"] == "kept_extractor_missing":
            assert coverage == "extractor_missing", code
        else:
            assert coverage == "executable", code
            assert code in PROMOTED, code


def test_counting_and_geometry_rules_are_never_promoted() -> None:
    """Подсчёт, площадь по контуру и обмер по чертежу не становятся текстом."""
    forbidden = {
        "object_counting",
        "area_from_polygon",
        "drawing_measurement",
        "zone_geometry",
        "slope_from_geometry",
        "schedule_chart",
        "daylight_calculation",
    }
    for entry in _entries():
        if entry.get("reason_code") in forbidden:
            assert entry["decision"] == "kept_extractor_missing", entry["code"]
            assert _REGISTRY.get(str(entry["code"]))["coverage"] == "extractor_missing"


def test_promoted_entries_record_their_anchors() -> None:
    for entry in _entries():
        if entry["decision"] != "promoted_executable":
            continue
        anchors = entry["anchors"]
        assert isinstance(anchors, list) and len(anchors) >= 3, entry["code"]
        assert anchors == _REGISTRY.get(str(entry["code"]))["extractor"]["anchors"]
