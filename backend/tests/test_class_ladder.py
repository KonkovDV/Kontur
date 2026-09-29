"""Инварианты триажа «лестниц классов» (data/matrix/class_ladder_triage.json).

Проверяем, что выборка воспроизводима из правил, решения по ней полные и
непротиворечивые, а пять переведённых правил действительно исполнимы:
регулярка покрывает каждый член лестницы и не ловит значения вне домена.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from kontur.application.comparators import fold_homoglyphs
from kontur.application.extractors.text import _normalize
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
MATRIX = REPO / "data" / "matrix"
TRIAGE = MATRIX / "class_ladder_triage.json"

_REGISTRY = FileRuleRegistry(MATRIX)

PROMOTED = ("KR-056", "KR-057", "PPM-103", "PPM-107", "ZU-124")

# Для каждого правила: что лежит в тексте → какое значение лестницы должно извлечься.
LADDER_PROBES: dict[str, tuple[tuple[str, str], ...]] = {
    "KR-056": (
        ("С235", "С235"),
        ("С245", "С245"),
        ("С255", "С255"),
        ("С275", "С275"),
        ("С285", "С285"),
        ("С345", "С345"),
        ("С355", "С355"),
        ("С375", "С375"),
        ("С390", "С390"),
        ("С440", "С440"),
        ("С550", "С550"),
        ("С590", "С590"),
    ),
    "KR-057": (
        ("А240", "А240"),
        ("А400", "А400"),
        ("А500", "А500"),
        ("А600", "А600"),
        ("А800", "А800"),
        ("А1000", "А1000"),
    ),
    "PPM-103": (
        ("EI 15", "15"),
        ("EI 30", "30"),
        ("EI 45", "45"),
        ("EI 60", "60"),
        ("EI 90", "90"),
        ("EI 120", "120"),
        ("EI 150", "150"),
        ("EI 180", "180"),
    ),
    "PPM-107": (
        ("КМ0", "КМ0"),
        ("КМ1", "КМ1"),
        ("КМ2", "КМ2"),
        ("КМ3", "КМ3"),
        ("КМ4", "КМ4"),
        ("КМ5", "КМ5"),
    ),
    "ZU-124": (
        ("A++", "A++"),
        ("A+", "A+"),
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
        ("E", "E"),
        ("F", "F"),
        ("G", "G"),
    ),
}

# Значения вне домена: регулярка не должна отдавать член лестницы.
OUT_OF_LADDER: dict[str, tuple[str, ...]] = {
    "KR-056": ("С300", "С2355"),
    "KR-057": ("А300", "А4000"),
    "PPM-103": ("EI 25", "EI 200"),
    "PPM-107": ("КМ6", "КМ12"),
    "ZU-124": ("H", "A+++"),
}


def _triage() -> dict[str, object]:
    return json.loads(TRIAGE.read_text(encoding="utf-8"))


def _entries() -> list[dict[str, object]]:
    entries = _triage()["entries"]
    assert isinstance(entries, list)
    return entries


def _surveyed_codes() -> set[str]:
    out: set[str] = set()
    for code in _REGISTRY.all_codes():
        rule = _REGISTRY.get(code)
        unit = str(rule.get("unit") or "")
        operator = str((rule.get("comparator") or {}).get("operator") or "")
        if operator == "class_not_lower" or "Класс" in unit or "Марка" in unit:
            out.add(code)
    return out


def test_triage_file_exists_and_is_json() -> None:
    assert TRIAGE.is_file()
    assert isinstance(_triage(), dict)


def test_triage_covers_exactly_the_surveyed_codes() -> None:
    """Выборка воспроизводима из правил, а не зафиксирована руками."""
    assert {str(e["code"]) for e in _entries()} == _surveyed_codes()


def test_triage_does_not_claim_gate_j() -> None:
    triage = _triage()
    assert triage["closes_gate_j"] is False
    assert "132/132" in str(triage["note"])


def test_decision_counts_match_entries() -> None:
    triage = _triage()
    counts = triage["decision_counts"]
    assert isinstance(counts, dict)
    actual: dict[str, int] = {}
    for entry in _entries():
        actual[str(entry["decision"])] = actual.get(str(entry["decision"]), 0) + 1
    assert counts == actual
    assert triage["total_surveyed"] == len(_entries())


def test_every_entry_has_a_rationale() -> None:
    for entry in _entries():
        assert str(entry["rationale"]).strip(), entry["code"]
        assert entry["decision"] in {
            "already_executable",
            "kept_extractor_missing",
            "promoted_executable",
        }


def test_decision_agrees_with_coverage_in_matrix() -> None:
    for entry in _entries():
        code = str(entry["code"])
        coverage = _REGISTRY.get(code)["coverage"]
        if entry["decision"] == "kept_extractor_missing":
            assert coverage == "extractor_missing", code
            assert str(entry["reason_code"]).strip(), code
        else:
            assert coverage == "executable", code


def test_promoted_rules_are_enum_plus_class_not_lower() -> None:
    for code in PROMOTED:
        rule = _REGISTRY.get(code)
        assert rule["coverage"] == "executable", code
        assert rule["extractor"]["type"] == "enum", code
        assert rule["comparator"]["operator"] == "class_not_lower", code
        assert rule["extractor"]["dual_read_required"] is True, code
        assert rule["review_priority"] == "HIGH", code
        assert rule["extractor"]["normalization"] == ["nfc", "collapse_spaces", "upper"], code
        assert len(rule["extractor"]["anchors"]) >= 1, code
        assert len(rule["comparator"]["value"]) >= 6, code


def test_promoted_rules_have_four_fixtures_each() -> None:
    expected = {
        "same_class_gives_no_difference",
        "better_class_in_rd_is_not_violation",
        "lower_class_gives_candidate",
        "required_stage_absent_gives_missing_evidence",
    }
    for code in PROMOTED:
        names = {str(t["name"]) for t in _REGISTRY.get(code)["tests"]}
        assert names == expected, code


def test_probe_tables_cover_every_ladder_member() -> None:
    for code in PROMOTED:
        ladder = set(_REGISTRY.get(code)["comparator"]["value"])
        probed = {value for _, value in LADDER_PROBES[code]}
        assert probed == ladder, code


def test_regex_extracts_every_ladder_member() -> None:
    steps = ("nfc", "collapse_spaces", "upper")
    for code in PROMOTED:
        pattern = re.compile(str(_REGISTRY.get(code)["extractor"]["regex"]), re.IGNORECASE)
        for raw, expected in LADDER_PROBES[code]:
            match = pattern.search(raw)
            assert match is not None, (code, raw)
            got = _normalize(match.group(0), steps).replace(" ", "")
            assert got == _normalize(expected, steps).replace(" ", ""), (code, raw, got)


def test_regex_rejects_values_outside_the_ladder() -> None:
    for code in PROMOTED:
        pattern = re.compile(str(_REGISTRY.get(code)["extractor"]["regex"]), re.IGNORECASE)
        ladder = {fold_homoglyphs(v.upper()) for v in _REGISTRY.get(code)["comparator"]["value"]}
        for raw in OUT_OF_LADDER[code]:
            match = pattern.search(raw)
            if match is None:
                continue
            got = fold_homoglyphs(match.group(0).upper().replace(" ", ""))
            assert got not in ladder or got != fold_homoglyphs(raw.upper()), (code, raw, got)


def test_homoglyph_fold_maps_cyrillic_to_latin_but_keeps_roman_i() -> None:
    assert fold_homoglyphs("С245") == fold_homoglyphs("C245")
    assert fold_homoglyphs("А500") == fold_homoglyphs("A500")
    assert fold_homoglyphs("КМ1") == fold_homoglyphs("KM1")
    # Латинская I не сворачивается: римские цифры PZ-022 должны остаться как есть.
    assert fold_homoglyphs("III") == "III"
