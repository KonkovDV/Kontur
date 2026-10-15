"""Пороги проверяются по консервативной границе интервала, не по точечной оценке."""

from __future__ import annotations

import pytest

from kontur.evaluation.metrics import (
    INTERNAL_TARGETS,
    IOU_THRESHOLD,
    TZ_THRESHOLDS,
    Interval,
    character_accuracy,
    evidence_localization_interval,
    f1,
    iou,
    key_field_exact_match,
    key_field_exact_match_interval,
    meets_threshold,
    pooled_ca_line_bootstrap,
    pooled_character_accuracy,
    score_key_fields,
    wilson,
)

UNIT_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
UNIT_SQUARE_CW = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))


def test_wilson_on_empty_sample_is_uninformative() -> None:
    interval = wilson(0, 0)
    assert (interval.low, interval.high) == (0.0, 1.0)


def test_small_sample_does_not_confirm_threshold() -> None:
    """10 из 10 — точечная оценка 1.0, но выборка не подтверждает 0,95."""

    interval = wilson(10, 10)
    assert interval.point == 1.0
    assert not meets_threshold("precision", interval)


def test_large_sample_confirms_threshold() -> None:
    interval = wilson(970, 1000)
    assert meets_threshold("precision", interval)


def test_fpr_checked_by_upper_bound() -> None:
    assert meets_threshold("false_positive_rate", wilson(30, 1000))
    assert not meets_threshold("false_positive_rate", wilson(100, 1000))


def test_f1_floor_is_stricter_than_precision_and_recall_floors() -> None:
    """P=0.90 и R=0.80 одновременно не закрывают порог F1=0.85."""

    assert TZ_THRESHOLDS["f1"] == 0.85
    harmonic = f1(TZ_THRESHOLDS["precision"], TZ_THRESHOLDS["recall"])
    assert round(harmonic, 4) == 0.8471
    assert harmonic < TZ_THRESHOLDS["f1"]


def test_internal_targets_are_stricter_than_tz() -> None:
    for name, threshold in TZ_THRESHOLDS.items():
        target = INTERNAL_TARGETS[name]
        if name == "false_positive_rate":
            assert target <= threshold
        else:
            assert target >= threshold


def test_interval_is_immutable() -> None:
    interval = Interval(point=0.5, low=0.4, high=0.6, n=100)
    assert interval.n == 100


def test_key_field_exact_match_is_case_sensitive_in_ciphers() -> None:
    assert key_field_exact_match("12345-PZ", "12345-PZ")
    assert not key_field_exact_match("12345-PZ", "12345-pz")


def test_key_field_exact_match_uses_nfc_and_collapses_spaces() -> None:
    assert key_field_exact_match("12345-PZ", "  12345-PZ  ")
    assert key_field_exact_match("café-1", "café-1")
    assert not key_field_exact_match("12345-PZ", None)
    assert not key_field_exact_match("12345-PZ", "   ")


def test_key_field_threshold_needs_wilson_lower_bound() -> None:
    """Точечная 1.0 на 10 полях не закрывает порог ТЗ 0.90."""

    pairs = [("12345-PZ", "12345-PZ")] * 10
    interval = key_field_exact_match_interval(pairs)
    assert interval.point == 1.0
    assert not meets_threshold("key_field_exact_match", interval)
    empty = key_field_exact_match_interval([])
    assert empty.n == 0
    assert not meets_threshold("key_field_exact_match", empty)


# --- character_accuracy (RT-2709-09, гейт I) ---


def test_character_accuracy_perfect_match_is_one() -> None:
    """Идентичные строки после NFC → CA = 1.0."""
    assert character_accuracy("12345-PZ", "12345-PZ") == pytest.approx(1.0)


def test_character_accuracy_one_substitution() -> None:
    # 1 замена из 4 символов: CER = 1/4 = 0.25, CA = 0.75
    assert character_accuracy("ABCD", "ABCE") == pytest.approx(0.75)


def test_character_accuracy_empty_both_is_one() -> None:
    assert character_accuracy("", "") == pytest.approx(1.0)


def test_character_accuracy_empty_hypothesis_is_zero() -> None:
    """Пустая гипотеза при непустом эталоне: все символы пропущены, CA = 0."""
    assert character_accuracy("ABC", "") == pytest.approx(0.0)


def test_character_accuracy_normalises_nfc() -> None:
    nfc = "café"    # U+00E9 precomposed
    nfd = "café"  # e + combining acute accent — тот же глиф после NFC
    assert character_accuracy(nfc, nfd) == pytest.approx(1.0)


def test_character_accuracy_collapses_extra_spaces() -> None:
    assert character_accuracy("A B C", "A  B  C") == pytest.approx(1.0)


def test_character_accuracy_is_not_binary() -> None:
    """CER даёт промежуточное значение — не binary как Exact Match."""
    score = character_accuracy("ABCDEF", "XBCDEF")
    assert 0.0 < score < 1.0


def test_character_accuracy_is_case_sensitive() -> None:
    """Регистр не сворачивается: шифр документа чувствителен к регистру."""
    assert character_accuracy("PZ-001", "pz-001") != pytest.approx(1.0)


def test_key_field_kind_below_quota_stays_out_of_the_summary() -> None:
    short = score_key_fields([{"kind": "CIPHER", "reference": "PZ-001", "hypothesis": "PZ-001"}])
    assert short["defined"] is False
    assert short["threshold_met"] is False
    assert "CIPHER" in short["kinds_below_quota"]


def test_stage_field_ignores_case_and_cipher_keeps_it() -> None:
    scored = score_key_fields(
        [
            {"kind": "STAGE", "reference": "ПД", "hypothesis": "пд"},
            {"kind": "CIPHER", "reference": "PZ-001", "hypothesis": "pz-001"},
        ]
    )
    by_kind = {item["kind"]: item for item in scored["by_kind"]}  # type: ignore[union-attr]
    assert by_kind["STAGE"]["em"] == pytest.approx(1.0)
    assert by_kind["CIPHER"]["em"] == pytest.approx(0.0)


def test_thirty_perfect_ciphers_do_not_meet_the_field_threshold() -> None:
    fields = [
        {"kind": "CIPHER", "reference": "PZ-001", "hypothesis": "PZ-001"} for _ in range(30)
    ]
    scored = score_key_fields(fields)
    cipher = next(item for item in scored["by_kind"] if item["kind"] == "CIPHER")  # type: ignore[union-attr]
    assert cipher["measured"] is True
    assert scored["defined"] is True
    assert scored["n"] == 30
    assert scored["threshold_met"] is False


def test_unknown_key_field_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="ROOM"):
        score_key_fields([{"kind": "ROOM", "reference": "1", "hypothesis": "1"}])


def test_pooled_ca_weights_by_characters_not_by_lines() -> None:
    """Одна ошибка в короткой строке и верная длинная: микро-CA выше среднего строк."""

    pairs = [("А", "Б"), ("АБВГДЕЖЗ", "АБВГДЕЖЗ")]
    pooled = pooled_character_accuracy(pairs)
    mean = (
        character_accuracy("А", "Б") + character_accuracy("АБВГДЕЖЗ", "АБВГДЕЖЗ")
    ) / 2
    assert pooled.edit_distance == 1
    assert pooled.ref_chars == 9
    assert pooled.point == pytest.approx(8 / 9)
    assert mean == pytest.approx(0.5)
    assert pooled.point != pytest.approx(mean)


def test_pooled_ca_ignores_an_empty_reference() -> None:
    pooled = pooled_character_accuracy([("", "xxx"), ("АБ", "АБ")])
    assert pooled.n_lines == 2
    assert pooled.ref_chars == 2
    assert pooled.point == pytest.approx(1.0)


def test_pooled_ca_on_no_characters_is_undefined() -> None:
    pooled = pooled_character_accuracy([("", ""), ("", "гипотеза")])
    assert pooled.point is None
    assert pooled.cer is None
    assert pooled.wer is None
    assert pooled.ref_chars == 0
    assert pooled.line_exact_match == pytest.approx(0.5)
    assert pooled_ca_line_bootstrap([("", "")]) is None


def test_ocr_normalization_collapses_any_whitespace_and_keeps_signs() -> None:
    assert character_accuracy("А\tБ\nВ", "А Б В") == pytest.approx(1.0)
    assert character_accuracy("ИОС4.2-кор3", "ИОС42кор3") != pytest.approx(1.0)
    assert character_accuracy("A", "А") != pytest.approx(1.0)


def test_wer_and_line_exact_match_are_not_character_accuracy() -> None:
    pooled = pooled_character_accuracy([("А Б", "А В")])
    assert pooled.ref_tokens == 2
    assert pooled.token_distance == 1
    assert pooled.wer == pytest.approx(0.5)
    assert pooled.line_exact_match == pytest.approx(0.0)
    assert pooled.cer == pytest.approx(1.0 - (pooled.point or 0.0))
    empty = pooled_character_accuracy(())
    assert empty.line_exact_match is None
    assert empty.wer is None


def test_line_bootstrap_does_not_decide_the_threshold() -> None:
    same = pooled_ca_line_bootstrap([("АБ", "АВ")] * 4, rounds=40, seed=7)
    assert same is not None
    assert same.low == pytest.approx(same.high)
    assert same.decides_threshold is False
    mixed = pooled_ca_line_bootstrap(
        [("А", "Б"), ("АБВГДЕЖЗ", "АБВГДЕЖЗ")],
        rounds=200,
        seed=7,
    )
    assert mixed is not None
    assert mixed.low < mixed.high
    assert mixed.decides_threshold is False


# --- IoU ---


def test_iou_identical_polygons() -> None:
    assert iou(UNIT_SQUARE, UNIT_SQUARE) == pytest.approx(1.0)


def test_iou_is_symmetric() -> None:
    other = ((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75))
    assert iou(UNIT_SQUARE, other) == pytest.approx(iou(other, UNIT_SQUARE))


def test_iou_cw_winding_matches_ccw() -> None:
    """Клиппинг чувствителен к обходу; метрика не должна зависеть от CW/CCW."""

    assert iou(UNIT_SQUARE, UNIT_SQUARE_CW) == pytest.approx(1.0)
    half = ((0.5, 0.0), (1.5, 0.0), (1.5, 1.0), (0.5, 1.0))
    assert iou(UNIT_SQUARE_CW, half) == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_iou_disjoint_polygons() -> None:
    far = ((10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0))
    assert iou(UNIT_SQUARE, far) == pytest.approx(0.0)


def test_iou_half_overlap() -> None:
    half = ((0.5, 0.0), (1.5, 0.0), (1.5, 1.0), (0.5, 1.0))
    assert iou(UNIT_SQUARE, half) == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_iou_shared_edge_has_zero_area() -> None:
    left = ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))
    right = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))
    assert iou(left, right) == pytest.approx(0.0, abs=1e-9)


def test_iou_triangle_inside_square() -> None:
    tri = ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0))
    assert iou(UNIT_SQUARE, tri) == pytest.approx(0.5, abs=1e-6)


def test_iou_empty_and_degenerate() -> None:
    line = ((0.0, 0.0), (1.0, 0.0))
    assert iou((), UNIT_SQUARE) == 0.0
    assert iou(UNIT_SQUARE, ()) == 0.0
    assert iou((), ()) == 0.0
    assert iou(line, UNIT_SQUARE) == 0.0


def test_iou_full_containment() -> None:
    large = ((-1.0, -1.0), (2.0, -1.0), (2.0, 2.0), (-1.0, 2.0))
    assert iou(UNIT_SQUARE, large) == pytest.approx(1.0 / 9.0, abs=1e-6)


def test_nan_polygon_does_not_score_as_perfect_overlap() -> None:
    """RT-2609-28: NaN в контуре не даёт IoU 1."""

    poisoned = ((0.0, 0.0), (1.0, 0.0), (float("nan"), 1.0), (0.0, 1.0))
    assert iou(UNIT_SQUARE, poisoned) == 0.0
    assert iou(poisoned, UNIT_SQUARE) == 0.0


def test_iou_is_clamped_to_unit_interval() -> None:
    for left, right in ((UNIT_SQUARE, UNIT_SQUARE), (UNIT_SQUARE, ())):
        result = iou(left, right)
        assert 0.0 <= result <= 1.0


def test_evidence_localization_all_pass_confirms_threshold() -> None:
    pairs = [(UNIT_SQUARE, UNIT_SQUARE)] * 100
    interval = evidence_localization_interval(pairs)
    assert interval.point == pytest.approx(1.0)
    assert meets_threshold("evidence_localization", interval)


def test_evidence_localization_all_fail_does_not_confirm() -> None:
    far = ((100.0, 100.0), (101.0, 100.0), (101.0, 101.0), (100.0, 101.0))
    interval = evidence_localization_interval([(UNIT_SQUARE, far)] * 50)
    assert interval.point == pytest.approx(0.0)
    assert not meets_threshold("evidence_localization", interval)


def test_evidence_localization_empty_pairs_do_not_confirm() -> None:
    interval = evidence_localization_interval([])
    assert interval.n == 0
    assert interval.low == pytest.approx(0.0)
    assert interval.high == pytest.approx(1.0)
    assert not meets_threshold("evidence_localization", interval)


def test_evidence_localization_uses_iou_threshold_not_tz_point() -> None:
    """Пара с IoU=1/3 не считается локализованной при пороге 0.50."""

    half = ((0.5, 0.0), (1.5, 0.0), (1.5, 1.0), (0.5, 1.0))
    assert iou(UNIT_SQUARE, half) < IOU_THRESHOLD
    interval = evidence_localization_interval([(UNIT_SQUARE, half)] * 100)
    assert interval.point == pytest.approx(0.0)
    assert not meets_threshold("evidence_localization", interval)


def test_key_fields_report_wilson_ci_per_kind() -> None:
    """ТЗ §14.3: по каждому из 5 полей — n и 95% CI; n < 30 порог не решает."""

    rows = [{"kind": "CIPHER", "reference": "АНО/1-П-АР", "hypothesis": "АНО/1-П-АР"}] * 40
    rows += [{"kind": "SHEET_PAGE", "reference": "3", "hypothesis": "3"}] * 5
    scored = score_key_fields(rows)
    by_kind = {item["kind"]: item for item in scored["by_kind"]}  # type: ignore[union-attr]
    cipher = by_kind["CIPHER"]
    assert cipher["n"] == 40 and cipher["ci95_high"] == pytest.approx(1.0)
    assert 0.90 < cipher["ci95_low"] < 1.0
    assert cipher["threshold_met"] is True
    sheet = by_kind["SHEET_PAGE"]
    assert sheet["ci95_low"] is not None and sheet["threshold_met"] is False
    assert by_kind["ROOM_ELEMENT"]["ci95_low"] is None
    assert by_kind["ROOM_ELEMENT"]["threshold_met"] is False
