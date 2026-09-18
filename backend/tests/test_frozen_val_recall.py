"""Gate N: Frozen validation recall/precision/F1/FPR gate.

Normal CI: all tests skip automatically (KONTUR_FROZEN_VAL_PATH not set).
RC freeze gate (28.09):
    KONTUR_FROZEN_VAL_PATH=data/frozen_val.jsonl pytest -m frozen_val -v --tb=short

Format frozen_val.jsonl (one JSON per line):
    {"label": "CANDIDATE", "predicted": "CANDIDATE"}
    {"label": "AUTO_NO_DIFFERENCE", "predicted": "AUTO_NO_DIFFERENCE"}

Positive labels: CANDIDATE, MISSING_EVIDENCE
Negative labels: everything else (AUTO_NO_DIFFERENCE, NOT_APPLICABLE, ABSTAIN, ...)

Refs: TZ p.14 acceptance thresholds, Gate N, GAP-IOS4-VAL.
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import NamedTuple

import pytest

_FROZEN_VAL_PATH_ENV = "KONTUR_FROZEN_VAL_PATH"
_POSITIVE_LABELS = frozenset({"CANDIDATE", "MISSING_EVIDENCE"})

pytestmark = pytest.mark.frozen_val


class _Metrics(NamedTuple):
    recall: float
    precision: float
    f1: float
    fpr: float
    tp: int
    fp: int
    fn: int
    tn: int
    n_total: int


def _is_positive(label: str) -> bool:
    return label in _POSITIVE_LABELS


def _load_metrics() -> _Metrics:
    path_str = os.getenv(_FROZEN_VAL_PATH_ENV, "")
    if not path_str:
        pytest.skip(
            f"{_FROZEN_VAL_PATH_ENV} is not set -- frozen_val gate skipped in normal CI"
        )
    path = pathlib.Path(path_str)
    if not path.exists():
        pytest.skip(f"frozen_val file not found: {path}")

    tp = fp = fn = tn = 0
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                pytest.fail(f"frozen_val.jsonl line {lineno}: invalid JSON -- {exc}")

            if "label" not in row or "predicted" not in row:
                pytest.fail(
                    f"frozen_val.jsonl line {lineno}: missing 'label' or 'predicted'"
                )

            gold = _is_positive(row["label"])
            pred = _is_positive(row["predicted"])

            if gold and pred:
                tp += 1
            elif not gold and pred:
                fp += 1
            elif gold and not pred:
                fn += 1
            else:
                tn += 1

    n_total = tp + fp + fn + tn
    if n_total == 0:
        pytest.fail("frozen_val.jsonl is empty or contains only blank lines")

    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return _Metrics(
        recall=recall,
        precision=precision,
        f1=f1,
        fpr=fpr,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        n_total=n_total,
    )


def test_frozen_val_has_positive_examples() -> None:
    """Sanity: dataset must contain at least 1 positive (CANDIDATE/MISSING_EVIDENCE) row."""
    m = _load_metrics()
    assert m.tp + m.fn >= 1, (
        f"frozen_val.jsonl has no positive-label rows (tp={m.tp}, fn={m.fn})."
    )


def test_frozen_val_recall() -> None:
    """Recall (TPR) >= 0.80 -- TZ p.14 gate.

    For 106 critical parameters recall must be 1.00 (Gate J).
    Skipping a critical parameter caps the score at 59/100.
    """
    m = _load_metrics()
    threshold = 0.80
    assert m.recall >= threshold, (
        f"GATE FAILED: Recall = {m.recall:.4f} < {threshold}. "
        f"tp={m.tp}, fn={m.fn}. "
        f"Each fn on a critical param = 59/100 score cap."
    )


def test_frozen_val_precision() -> None:
    """Precision >= 0.90 -- TZ p.14 gate."""
    m = _load_metrics()
    threshold = 0.90
    assert m.precision >= threshold, (
        f"GATE FAILED: Precision = {m.precision:.4f} < {threshold}. "
        f"tp={m.tp}, fp={m.fp}."
    )


def test_frozen_val_f1() -> None:
    """F1 >= 0.85 -- TZ p.14 gate.

    WARNING: harmonic mean of P=0.90 and R=0.80 is ~0.847 < 0.85.
    The floor of both thresholds does NOT clear F1. Need precision headroom.
    See PLAN_2026_09 stop-conditions 25.09.
    """
    m = _load_metrics()
    threshold = 0.85
    assert m.f1 >= threshold, (
        f"GATE FAILED: F1 = {m.f1:.4f} < {threshold}. "
        f"P={m.precision:.4f}, R={m.recall:.4f}. "
        f"P=0.90 + R=0.80 harmonic = 0.847 -- raise precision margin."
    )


def test_frozen_val_fpr() -> None:
    """FPR (False Positive Rate) <= 0.10 -- TZ p.14 gate."""
    m = _load_metrics()
    threshold = 0.10
    assert m.fpr <= threshold, (
        f"GATE FAILED: FPR = {m.fpr:.4f} > {threshold}. "
        f"fp={m.fp}, tn={m.tn}."
    )
