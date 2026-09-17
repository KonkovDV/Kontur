"""\u041f\u043e\u0440\u043e\u0433\u0438 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u044e\u0442\u0441\u044f \u043f\u043e \u043a\u043e\u043d\u0441\u0435\u0440\u0432\u0430\u0442\u0438\u0432\u043d\u043e\u0439 \u0433\u0440\u0430\u043d\u0438\u0446\u0435 \u0438\u043d\u0442\u0435\u0440\u0432\u0430\u043b\u0430, \u043d\u0435 \u043f\u043e \u0442\u043e\u0447\u0435\u0447\u043d\u043e\u0439 \u043e\u0446\u0435\u043d\u043a\u0435."""

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
    wilson,
)

UNIT_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
UNIT_SQUARE_CW = ((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0))


def test_wilson_on_empty_sample_is_uninformative() -> None:
    interval = wilson(0, 0)
    assert (interval.low, interval.high) == (0.0, 1.0)


def test_small_sample_does_not_confirm_threshold() -> None:
    """10 \u0438\u0437 10 \u2014 \u0442\u043e\u0447\u0435\u0447\u043d\u0430\u044f \u043e\u0446\u0435\u043d\u043a\u0430 1.0, \u043d\u043e \u0432\u044b\u0431\u043e\u0440\u043a\u0430 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u0435\u0442 0,95."""

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
    """P=0.90 \u0438 R=0.80 \u043e\u0434\u043d\u043e\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043d\u0435 \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u044e\u0442 \u043f\u043e\u0440\u043e\u0433 F1=0.85."""

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
    assert key_field_exact_match("caf\u00e9-1", "cafe\u0301-1")
    assert not key_field_exact_match("12345-PZ", None)
    assert not key_field_exact_match("12345-PZ", "   ")


def test_key_field_threshold_needs_wilson_lower_bound() -> None:
    """\u0422\u043e\u0447\u0435\u0447\u043d\u0430\u044f 1.0 \u043d\u0430 10 \u043f\u043e\u043b\u044f\u0445 \u043d\u0435 \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0435\u0442 \u043f\u043e\u0440\u043e\u0433 \u0422\u0417 0.90."""

    pairs = [("12345-PZ", "12345-PZ")] * 10
    interval = key_field_exact_match_interval(pairs)
    assert interval.point == 1.0
    assert not meets_threshold("key_field_exact_match", interval)
    empty = key_field_exact_match_interval([])
    assert empty.n == 0
    assert not meets_threshold("key_field_exact_match", empty)


# --- character_accuracy (RT-2709-09, \u0433\u0435\u0439\u0442 I) ---


def test_character_accuracy_perfect_match_is_one() -> None:
    """\u0418\u0434\u0435\u043d\u0442\u0438\u0447\u043d\u044b\u0435 \u0441\u0442\u0440\u043e\u043a\u0438 \u043f\u043e\u0441\u043b\u0435 NFC \u2192 CA = 1.0."""
    assert character_accuracy("12345-PZ", "12345-PZ") == pytest.approx(1.0)


def test_character_accuracy_one_substitution() -> None:
    # 1 \u0437\u0430\u043c\u0435\u043d\u0430 \u0438\u0437 4 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432: CER = 1/4 = 0.25, CA = 0.75
    assert character_accuracy("ABCD", "ABCE") == pytest.approx(0.75)


def test_character_accuracy_empty_both_is_one() -> None:
    assert character_accuracy("", "") == pytest.approx(1.0)


def test_character_accuracy_empty_hypothesis_is_zero() -> None:
    """\u041f\u0443\u0441\u0442\u0430\u044f \u0433\u0438\u043f\u043e\u0442\u0435\u0437\u0430 \u043f\u0440\u0438 \u043d\u0435\u043f\u0443\u0441\u0442\u043e\u043c \u044d\u0442\u0430\u043b\u043e\u043d\u0435: \u0432\u0441\u0435 \u0441\u0438\u043c\u0432\u043e\u043b\u044b \u043f\u0440\u043e\u043f\u0443\u0449\u0435\u043d\u044b, CA = 0."""
    assert character_accuracy("ABC", "") == pytest.approx(0.0)


def test_character_accuracy_normalises_nfc() -> None:
    nfc = "caf\u00e9"    # U+00E9 precomposed
    nfd = "cafe\u0301"  # e + combining acute accent \u2014 \u0442\u043e\u0442 \u0436\u0435 \u0433\u043b\u0438\u0444 \u043f\u043e\u0441\u043b\u0435 NFC
    assert character_accuracy(nfc, nfd) == pytest.approx(1.0)


def test_character_accuracy_collapses_extra_spaces() -> None:
    assert character_accuracy("A B C", "A  B  C") == pytest.approx(1.0)


def test_character_accuracy_is_not_binary() -> None:
    """CER \u0434\u0430\u0451\u0442 \u043f\u0440\u043e\u043c\u0435\u0436\u0443\u0442\u043e\u0447\u043d\u043e\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u2014 \u043d\u0435 binary \u043a\u0430\u043a Exact Match."""
    score = character_accuracy("ABCDEF", "XBCDEF")
    assert 0.0 < score < 1.0


def test_character_accuracy_is_case_sensitive() -> None:
    """\u0420\u0435\u0433\u0438\u0441\u0442\u0440 \u043d\u0435 \u0441\u0432\u043e\u0440\u0430\u0447\u0438\u0432\u0430\u0435\u0442\u0441\u044f: \u0448\u0438\u0444\u0440 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430 \u0447\u0443\u0432\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u0435\u043d \u043a \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0443."""
    assert character_accuracy("PZ-001", "pz-001") != pytest.approx(1.0)


# --- IoU ---


def test_iou_identical_polygons() -> None:
    assert iou(UNIT_SQUARE, UNIT_SQUARE) == pytest.approx(1.0)


def test_iou_is_symmetric() -> None:
    other = ((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75))
    assert iou(UNIT_SQUARE, other) == pytest.approx(iou(other, UNIT_SQUARE))


def test_iou_cw_winding_matches_ccw() -> None:
    """\u041a\u043b\u0438\u043f\u043f\u0438\u043d\u0433 \u0447\u0443\u0432\u0441\u0442\u0432\u0438\u0442\u0435\u043b\u0435\u043d \u043a \u043e\u0431\u0445\u043e\u0434\u0443; \u043c\u0435\u0442\u0440\u0438\u043a\u0430 \u043d\u0435 \u0434\u043e\u043b\u0436\u043d\u0430 \u0437\u0430\u0432\u0438\u0441\u0435\u0442\u044c \u043e\u0442 CW/CCW."""

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
    """\u041f\u0430\u0440\u0430 \u0441 IoU=1/3 \u043d\u0435 \u0441\u0447\u0438\u0442\u0430\u0435\u0442\u0441\u044f \u043b\u043e\u043a\u0430\u043b\u0438\u0437\u043e\u0432\u0430\u043d\u043d\u043e\u0439 \u043f\u0440\u0438 \u043f\u043e\u0440\u043e\u0433\u0435 0.50."""

    half = ((0.5, 0.0), (1.5, 0.0), (1.5, 1.0), (0.5, 1.0))
    assert iou(UNIT_SQUARE, half) < IOU_THRESHOLD
    interval = evidence_localization_interval([(UNIT_SQUARE, half)] * 100)
    assert interval.point == pytest.approx(0.0)
    assert not meets_threshold("evidence_localization", interval)
