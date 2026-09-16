"""Канонизация кодов матрицы и display-алиасы Приложения 2."""

from __future__ import annotations

from kontur.domain.rule_codes import canonicalize_rule_code, display_alias


def test_three_digit_codes_are_stable() -> None:
    assert canonicalize_rule_code("PZ-001") == "PZ-001"
    assert canonicalize_rule_code("IOS4-079") == "IOS4-079"


def test_short_forms_pad_to_three_digits() -> None:
    assert canonicalize_rule_code("pz-1") == "PZ-001"
    assert canonicalize_rule_code("AR-14") == "AR-014"
    assert canonicalize_rule_code("KR-55") == "KR-055"


def test_display_alias_matches_appendix2() -> None:
    assert display_alias("AR-014") == "AR-14"
    assert display_alias("KR-055") == "KR-55"
    assert display_alias("PZ-001") == "PZ-1"


def test_free_search_code_is_left_intact() -> None:
    assert canonicalize_rule_code("FREE-HEATING-001") == "FREE-HEATING-001"
