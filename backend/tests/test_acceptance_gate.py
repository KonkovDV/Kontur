"""Пустой замер гейтов I/J/K/L не становится сдачей."""

from __future__ import annotations

from kontur.evaluation.acceptance_gate import (
    STATUS_BAD,
    STATUS_MISSING,
    STATUS_OK,
    judge_gates,
)
from kontur.evaluation.metrics import meets_threshold, wilson


def test_six_of_six_public_gold_does_not_meet_recall() -> None:
    assert meets_threshold("recall", wilson(6, 6)) is False


def test_missing_measurements_block_the_gates() -> None:
    report = judge_gates({})
    assert report["verdict"] == STATUS_MISSING
    assert report["closes_release"] is False
    assert report["gates"] == {
        "I": STATUS_MISSING,
        "J": STATUS_MISSING,
        "K": STATUS_MISSING,
        "L": STATUS_MISSING,
    }


def test_a_failed_ocr_gate_is_fail_not_incomplete() -> None:
    report = judge_gates(
        {
            "ocr": {"measured": True, "closes_gate_i": False},
            "frozen_val": {"measured": True, "closes_gate_j": True},
            "usability": {"users": 5, "closes_gate_k": True},
            "timings": {"measured": True, "within_limits": True},
        }
    )
    assert report["verdict"] == STATUS_BAD
    assert report["gates"]["I"] == STATUS_BAD
    assert report["closes_release"] is False


def test_silver_ocr_stays_incomplete_instead_of_a_failed_gold_gate() -> None:
    report = judge_gates(
        {
            "ocr": {"measured": True, "closes_gate_i": False, "gold": False},
            "frozen_val": {"measured": False},
            "usability": {"users": 0, "closes_gate_k": False},
            "timings": {"measured": False, "within_limits": False},
        }
    )
    assert report["gates"]["I"] == STATUS_MISSING
    assert report["verdict"] == STATUS_MISSING


def test_gates_pass_only_when_every_measurement_meets_its_threshold() -> None:
    report = judge_gates(
        {
            "ocr": {"measured": True, "closes_gate_i": True},
            "frozen_val": {"measured": True, "closes_gate_j": True},
            "usability": {"users": 5, "closes_gate_k": True},
            "timings": {"measured": True, "within_limits": True},
        }
    )
    assert report["verdict"] == STATUS_OK
    assert report["closes_release"] is True
