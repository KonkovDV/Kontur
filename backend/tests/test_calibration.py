import random

import pytest

from kontur.evaluation.calibration import (
    Sample,
    calibration_report,
    choose_t_high,
    ece,
    load_samples,
    reliability_svg,
)


def _synthetic(calibrated: bool, n: int = 4000) -> list[Sample]:
    rng = random.Random(7)  # noqa: S311 - синтетика для теста
    out = []
    for _ in range(n):
        c = rng.random()
        p = c if calibrated else 1 - c
        out.append(Sample(c, rng.random() < p))
    return out


def test_ece_perfect_near_zero_broken_large():
    assert ece(_synthetic(True)) < 0.03
    assert ece(_synthetic(False)) > 0.3


def test_hidden_split_rejected():
    with pytest.raises(ValueError):
        load_samples([{"confidence": 0.9, "correct": True, "split": "hidden"}])


def test_empty_is_uncalibrated_and_never_closes_gate():
    r = calibration_report([])
    assert r["status"] == "uncalibrated" and r["t_high"] is None
    assert r["closes_gate"] is False and r["is_gold"] is False and r["n"] == 0
    assert "<svg" in reliability_svg(r)


def test_t_high_uses_wilson_upper_bound():
    pick = choose_t_high(_synthetic(True), max_error_rate=0.10)
    assert pick is not None and pick["error_rate_ci95"][1] <= 0.10
    assert choose_t_high(_synthetic(False), max_error_rate=0.10) is None
