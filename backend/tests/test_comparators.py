"""Тесты всех компараторов (Гейт H).

Проверяем:
  - delta    (abs/rel/zero допуск)
  - eq, ne, lt, le, gt, ge  (числовые)
  - range    (диапазон)
  - in_set, not_in_set  (множества)
  - class_not_lower  (упорядоченный класс)
  - present  (присутствие)
  - compare_values (роутер)
"""

from __future__ import annotations

import pytest

from kontur.application.comparators import (
    ALL_OPERATORS,
    NUMERIC_OPERATORS,
    Comparison,
    compare_class_not_lower,
    compare_delta,
    compare_ordering,
    compare_presence,
    compare_range,
    compare_set_membership,
    compare_values,
)
from kontur.domain.statuses import FindingStatus

# ── фикстуры правил ──────────────────────────────────────────────────────────────


def _rule(operator: str, **extra: object) -> dict[str, object]:
    """Mini-rule для одного оператора."""
    comparator: dict[str, object] = {"operator": operator, **extra}
    return {"code": "TST-001", "unit": "м²", "comparator": comparator}


BETON_ORDERED = [
    "B7.5", "B10", "B12.5", "B15", "B20", "B22.5",
    "B25", "B30", "B35", "B40", "B45", "B50", "B55", "B60",
]


# ── delta ───────────────────────────────────────────────────────────────────────


class TestCompareDelta:
    def test_equal_zero_tol_gives_no_diff(self) -> None:
        rule = _rule("delta", tolerance_abs=0.0)
        r = compare_delta(100.0, 100.0, rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE
        assert r.delta == 0.0

    def test_any_diff_with_zero_tol_is_candidate(self) -> None:
        rule = _rule("delta", tolerance_abs=0.0)
        r = compare_delta(100.0, 101.0, rule)
        assert r.status == FindingStatus.CANDIDATE
        assert r.delta == pytest.approx(1.0)

    def test_within_abs_tolerance(self) -> None:
        rule = _rule("delta", tolerance_abs=5.0)
        r = compare_delta(100.0, 104.9, rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_outside_abs_tolerance(self) -> None:
        rule = _rule("delta", tolerance_abs=5.0)
        r = compare_delta(100.0, 106.0, rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_within_rel_tolerance(self) -> None:
        rule = _rule("delta", tolerance_rel=0.05)  # 5 %
        r = compare_delta(100.0, 104.0, rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_outside_rel_tolerance(self) -> None:
        rule = _rule("delta", tolerance_rel=0.02)  # 2 %
        r = compare_delta(100.0, 110.0, rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_no_tolerance_uses_exact_equality(self) -> None:
        rule = {"code": "TST", "unit": "", "comparator": {"operator": "delta"}}
        assert compare_delta(5.0, 5.0, rule).status == FindingStatus.AUTO_NO_DIFFERENCE
        assert compare_delta(5.0, 5.1, rule).status == FindingStatus.CANDIDATE

    def test_negative_delta(self) -> None:
        rule = _rule("delta", tolerance_abs=0.0)
        r = compare_delta(200.0, 190.0, rule)
        assert r.status == FindingStatus.CANDIDATE
        assert r.delta == pytest.approx(-10.0)

    def test_comparison_does_not_allow_human_verdict(self) -> None:
        rule = _rule("delta", tolerance_abs=0.0)
        r = compare_delta(1.0, 1.0, rule)
        assert r.status not in {
            FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED
        }


# ── ordering (eq/ne/lt/le/gt/ge) ─────────────────────────────────────────


class TestCompareOrdering:
    @pytest.mark.parametrize(
        "op, exp, act, expected_status",
        [
            ("eq", 5.0, 5.0, FindingStatus.AUTO_NO_DIFFERENCE),
            ("eq", 5.0, 6.0, FindingStatus.CANDIDATE),
            ("ne", 5.0, 6.0, FindingStatus.AUTO_NO_DIFFERENCE),
            ("ne", 5.0, 5.0, FindingStatus.CANDIDATE),
            ("lt", 5.0, 4.0, FindingStatus.AUTO_NO_DIFFERENCE),
            ("lt", 5.0, 5.0, FindingStatus.CANDIDATE),
            ("le", 5.0, 5.0, FindingStatus.AUTO_NO_DIFFERENCE),
            ("le", 5.0, 6.0, FindingStatus.CANDIDATE),
            ("gt", 5.0, 6.0, FindingStatus.AUTO_NO_DIFFERENCE),
            ("gt", 5.0, 5.0, FindingStatus.CANDIDATE),
            ("ge", 0.9, 0.9, FindingStatus.AUTO_NO_DIFFERENCE),
            ("ge", 0.9, 0.8, FindingStatus.CANDIDATE),
            ("ge", 0.9, 1.2, FindingStatus.AUTO_NO_DIFFERENCE),
        ],
    )
    def test_operator(
        self,
        op: str,
        exp: float,
        act: float,
        expected_status: FindingStatus,
    ) -> None:
        rule = _rule(op, value=exp)
        r = compare_ordering(exp, act, rule)
        assert r.status == expected_status

    def test_ge_uses_value_not_expected_when_provided(self) -> None:
        rule = _rule("ge", value=0.9)
        r = compare_ordering(expected=999.0, actual=1.0, rule=rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE
        assert r.expected == pytest.approx(0.9)

    def test_ge_falls_back_to_expected_when_no_value(self) -> None:
        rule = {"code": "TST", "unit": "", "comparator": {"operator": "ge"}}
        r = compare_ordering(expected=5.0, actual=5.0, rule=rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_unknown_operator_raises(self) -> None:
        with pytest.raises(ValueError, match="compare_ordering"):
            rule = _rule("delta")
            compare_ordering(1.0, 1.0, rule)


# ── range ─────────────────────────────────────────────────────────────────────


class TestCompareRange:
    def test_inside_range(self) -> None:
        rule = _rule("range", min_value=10.0, max_value=20.0)
        r = compare_range(15.0, 15.0, rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_below_min(self) -> None:
        rule = _rule("range", min_value=10.0, max_value=20.0)
        r = compare_range(15.0, 5.0, rule)
        assert r.status == FindingStatus.CANDIDATE
        assert "нижняя граница" in r.rationale

    def test_above_max(self) -> None:
        rule = _rule("range", min_value=10.0, max_value=20.0)
        r = compare_range(15.0, 25.0, rule)
        assert r.status == FindingStatus.CANDIDATE
        assert "верхняя граница" in r.rationale

    def test_at_boundary_min(self) -> None:
        rule = _rule("range", min_value=10.0, max_value=20.0)
        assert compare_range(15.0, 10.0, rule).status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_at_boundary_max(self) -> None:
        rule = _rule("range", min_value=10.0, max_value=20.0)
        assert compare_range(15.0, 20.0, rule).status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_only_min_bound(self) -> None:
        rule = _rule("range", min_value=5.0)
        assert compare_range(5.0, 5.0, rule).status == FindingStatus.AUTO_NO_DIFFERENCE
        assert compare_range(5.0, 3.0, rule).status == FindingStatus.CANDIDATE

    def test_only_max_bound(self) -> None:
        rule = _rule("range", max_value=10.0)
        assert compare_range(5.0, 10.0, rule).status == FindingStatus.AUTO_NO_DIFFERENCE
        assert compare_range(5.0, 11.0, rule).status == FindingStatus.CANDIDATE


# ── set membership ───────────────────────────────────────────────────────────


class TestCompareSetMembership:
    def test_in_set_present(self) -> None:
        rule = _rule("in_set", value=["A", "B", "C"])
        r = compare_set_membership("B", rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_in_set_absent(self) -> None:
        rule = _rule("in_set", value=["A", "B", "C"])
        r = compare_set_membership("D", rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_not_in_set_absent(self) -> None:
        rule = _rule("not_in_set", value=["X", "Y"])
        r = compare_set_membership("Z", rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_not_in_set_present(self) -> None:
        rule = _rule("not_in_set", value=["X", "Y"])
        r = compare_set_membership("X", rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_case_insensitive(self) -> None:
        rule = _rule("in_set", value=["Approved"])
        assert compare_set_membership("approved", rule).status == FindingStatus.AUTO_NO_DIFFERENCE
        assert compare_set_membership("APPROVED", rule).status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_empty_set_always_absent(self) -> None:
        rule = _rule("in_set", value=[])
        assert compare_set_membership("anything", rule).status == FindingStatus.CANDIDATE


# ── class_not_lower ─────────────────────────────────────────────────────────


class TestCompareClassNotLower:
    def _kr055_rule(self) -> dict[str, object]:
        return {
            "code": "KR-055",
            "unit": "Марка (B)",
            "comparator": {
                "operator": "class_not_lower",
                "value": BETON_ORDERED,
            },
        }

    def test_same_class_is_no_difference(self) -> None:
        r = compare_class_not_lower("B35", "B35", self._kr055_rule())
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE
        assert r.delta == 0.0

    def test_lower_class_is_candidate(self) -> None:
        r = compare_class_not_lower("B35", "B30", self._kr055_rule())
        assert r.status == FindingStatus.CANDIDATE
        assert r.delta < 0
        assert "понижение" in r.rationale

    def test_higher_class_is_no_difference(self) -> None:
        r = compare_class_not_lower("B30", "B35", self._kr055_rule())
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE
        assert r.delta > 0

    def test_b22_5_not_confused_with_b22(self) -> None:
        r = compare_class_not_lower("B22.5", "B22.5", self._kr055_rule())
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE
        r2 = compare_class_not_lower("B25", "B22.5", self._kr055_rule())
        assert r2.status == FindingStatus.CANDIDATE

    def test_empty_ordered_list_raises(self) -> None:
        rule = {"code": "TST", "unit": "", "comparator": {"operator": "class_not_lower", "value": []}}
        with pytest.raises(ValueError, match="class_not_lower"):
            compare_class_not_lower("B35", "B30", rule)

    def test_unknown_class_raises(self) -> None:
        rule = self._kr055_rule()
        with pytest.raises(ValueError, match="B99"):
            compare_class_not_lower("B35", "B99", rule)

    def test_case_insensitive_lookup(self) -> None:
        rule = self._kr055_rule()
        r = compare_class_not_lower("b35", "b35", rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE


# ── present ────────────────────────────────────────────────────────────────────


class TestComparePresence:
    def test_present_value_is_no_difference(self) -> None:
        rule = _rule("present")
        r = compare_presence("B35", rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE
        assert r.actual == 1.0

    def test_none_is_missing_evidence(self) -> None:
        rule = _rule("present")
        r = compare_presence(None, rule)
        assert r.status == FindingStatus.MISSING_EVIDENCE
        assert r.status is not FindingStatus.CANDIDATE
        assert r.actual == 0.0

    def test_empty_string_is_missing_evidence(self) -> None:
        rule = _rule("present")
        assert compare_presence("", rule).status == FindingStatus.MISSING_EVIDENCE

    def test_nonzero_float_is_present(self) -> None:
        rule = _rule("present")
        assert compare_presence(42.0, rule).status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_zero_float_is_absent(self) -> None:
        rule = _rule("present")
        assert compare_presence(0.0, rule).status == FindingStatus.MISSING_EVIDENCE


# ── compare_values роутер ────────────────────────────────────────────────────


class TestCompareValues:
    def test_routes_delta(self) -> None:
        rule = _rule("delta", tolerance_abs=0.0)
        r = compare_values(100.0, 100.0, rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_routes_ge(self) -> None:
        rule = _rule("ge", value=0.9)
        r = compare_values(0.9, 0.85, rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_routes_eq(self) -> None:
        rule = _rule("eq", value=5.0)
        r = compare_values(5.0, 5.0, rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_routes_range(self) -> None:
        rule = _rule("range", min_value=0.0, max_value=10.0)
        r = compare_values(5.0, 15.0, rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_routes_in_set(self) -> None:
        rule = _rule("in_set", value=["OK", "PASS"])
        r = compare_values("OK", "OK", rule)
        assert r.status == FindingStatus.AUTO_NO_DIFFERENCE

    def test_routes_not_in_set(self) -> None:
        rule = _rule("not_in_set", value=["FAIL"])
        r = compare_values("", "FAIL", rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_routes_class_not_lower(self) -> None:
        rule = {
            "code": "KR-055",
            "unit": "B",
            "comparator": {"operator": "class_not_lower", "value": BETON_ORDERED},
        }
        r = compare_values("B35", "B30", rule)
        assert r.status == FindingStatus.CANDIDATE

    def test_routes_present(self) -> None:
        rule = _rule("present")
        r = compare_values("", None, rule)
        assert r.status == FindingStatus.MISSING_EVIDENCE
        assert r.status is not FindingStatus.CANDIDATE

    def test_unknown_operator_raises(self) -> None:
        rule = _rule("fuzzy_match")
        with pytest.raises(ValueError, match="fuzzy_match"):
            compare_values(1.0, 1.0, rule)

    def test_all_operators_covered(self) -> None:
        """Факт-чек: ALL_OPERATORS совпадает с rule.schema.json."""
        expected = {
            "delta", "eq", "ne", "lt", "le", "gt", "ge", "range",
            "in_set", "not_in_set", "class_not_lower", "present",
        }
        assert ALL_OPERATORS == expected

    def test_numeric_operators_subset(self) -> None:
        assert NUMERIC_OPERATORS == {"delta", "eq", "ne", "lt", "le", "gt", "ge", "range"}


# ── Comparison invariant ─────────────────────────────────────────────────────


class TestComparisonInvariant:
    @pytest.mark.parametrize(
        "forbidden",
        [FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED],
    )
    def test_human_verdict_raises(self, forbidden: FindingStatus) -> None:
        with pytest.raises(ValueError, match="человеческий"):
            Comparison(
                status=forbidden,
                expected=1.0,
                actual=1.0,
                delta=0.0,
                rationale="test",
            )
