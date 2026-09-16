"""Канонизация кодов матрицы, display-алиасы Приложения 2 и типографика источников."""

from __future__ import annotations

from kontur.domain.rule_codes import (
    canonicalize_rule_code,
    display_alias,
    fold_latin_homoglyphs,
    is_canonical_rule_code,
    normalize_code_text,
)


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


def test_typography_from_pdf_does_not_silently_break_the_code() -> None:
    """Неразрывный дефис, NBSP, en dash и полноширинные знаки — один и тот же код."""

    assert canonicalize_rule_code("AR\u2011014") == "AR-014"
    assert canonicalize_rule_code("AR\u2013014") == "AR-014"
    assert canonicalize_rule_code("AR\u2212014") == "AR-014"
    assert canonicalize_rule_code("PZ\u00a0-\u00a0001") == "PZ-001"
    assert canonicalize_rule_code("PZ\u202f-\u200b001") == "PZ-001"
    assert canonicalize_rule_code("\ufeffIOS4-79") == "IOS4-079"
    assert canonicalize_rule_code("\uff30\uff5a\uff0d\uff10\uff10\uff11") == "PZ-001"


def test_cyrillic_homoglyph_is_folded_only_when_result_is_latin() -> None:
    """`РZ-001` с русской «Р» — тот же PZ-001; настоящий кириллический код не портится."""

    assert canonicalize_rule_code("РZ-1") == "PZ-001"
    assert canonicalize_rule_code("АR-14") == "AR-014"
    assert canonicalize_rule_code("ПЗ-1") == "ПЗ-001"
    assert canonicalize_rule_code("ЗУ-1") == "ЗУ-001"
    assert fold_latin_homoglyphs("ЗУ-001") == "ЗУ-001"


def test_canonicalization_is_idempotent_and_self_reported() -> None:
    dirty = ["pz-1", "AR\u2011014", "РZ-1", "  SM-132  ", "FREE-HEATING-001", "ПЗ-1"]
    for code in dirty:
        once = canonicalize_rule_code(code)
        assert canonicalize_rule_code(once) == once
        assert is_canonical_rule_code(once)
    assert not is_canonical_rule_code("AR-14")
    assert not is_canonical_rule_code("ar-014")


def test_normalization_does_not_invent_a_code_from_garbage() -> None:
    assert canonicalize_rule_code("") == ""
    assert canonicalize_rule_code("   ") == ""
    assert canonicalize_rule_code("не код") == "НЕКОД"
    assert normalize_code_text("pz 1") == "PZ1"
