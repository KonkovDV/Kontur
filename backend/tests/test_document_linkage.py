"""W1 #2: метрика связки документов (§14.3) — без ложного Exact Match ≥0.95."""

from __future__ import annotations

import pytest

from kontur.evaluation.metrics import (
    LINKAGE_QUOTA,
    document_linkage_exact,
    meets_threshold,
    score_document_linkage,
    wilson,
)


def _row(ref: dict, hyp: dict) -> dict:
    return {"reference": ref, "hypothesis": hyp}


BASE = {
    "object_id": "OBJ-1",
    "stage": "PD",
    "document_code": "150321-АР",
    "revision": "2",
}


def test_exact_linkage_requires_all_four_fields() -> None:
    assert document_linkage_exact(BASE, dict(BASE))
    wrong_stage = dict(BASE, stage="RD")
    assert not document_linkage_exact(BASE, wrong_stage)
    stale_rev = dict(BASE, revision="1")
    assert not document_linkage_exact(BASE, stale_rev)
    other_obj = dict(BASE, object_id="OBJ-2")
    assert not document_linkage_exact(BASE, other_obj)


def test_score_below_quota_does_not_claim_threshold() -> None:
    groups = [_row(BASE, dict(BASE))] * 10
    scored = score_document_linkage(groups)
    assert scored["n"] == 10
    assert scored["measured"] is False
    assert scored["threshold_met"] is False
    assert scored["decides_threshold"] is False
    assert scored["em"] == pytest.approx(1.0)


def test_synthetic_wrong_stage_and_stale_revision() -> None:
    groups = [
        _row(BASE, dict(BASE)),
        _row(BASE, dict(BASE, stage="RD")),
        _row(BASE, dict(BASE, revision="1")),
    ]
    scored = score_document_linkage(groups)
    assert scored["matches"] == 1
    assert scored["n"] == 3
    assert scored["measured"] is False


def test_quota_met_can_decide_but_flags_not_gold() -> None:
    # Уильсон: 30/30 даёт ci_low ≈0.89 < 0.95 — честно threshold_met=false.
    at_quota = score_document_linkage([_row(BASE, dict(BASE))] * LINKAGE_QUOTA)
    assert at_quota["measured"] is True
    assert at_quota["is_gold"] is False
    assert at_quota["threshold_met"] is False
    # Нужен больший n при идеальном EM, чтобы нижняя граница ≥0.95.
    large = score_document_linkage([_row(BASE, dict(BASE))] * 120)
    assert large["measured"] is True
    assert large["threshold_met"] is True
    assert large["is_gold"] is False
    assert meets_threshold("document_linkage", wilson(large["matches"], large["n"]))
