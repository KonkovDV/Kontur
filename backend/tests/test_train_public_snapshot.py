"""Регрессия текущего TRAIN_PUBLIC snapshot; это не frozen validation."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_committed_train_public_snapshot_stays_blocked_at_l4() -> None:
    report = json.loads(
        (ROOT / "data" / "dataset" / "train_public_engineering.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["hits"] == 0
    assert report["recall_n"] == 6
    assert report["closes_gate_j"] is False
    assert report["gap_ios4_val_open"] is True
    assert report["gold_file_ids"] == ["F0171", "F0201"]
    assert report["stages_by_object"]["OBJ-TYUMENSKAYA-5-GOLD-SEED"] == [
        "PD",
        "RD",
    ]
    assert report["gold_finding_status"] == {
        "IOS4-078": "CLARIFICATION_REQUIRED",
        "IOS4-079": "CLARIFICATION_REQUIRED",
    }
    rationale = report["gold_finding_rationale"]
    assert rationale["IOS4-078"] == "PD: эталон без признака утверждения"
    assert rationale["IOS4-079"] == "PD: эталон без признака утверждения"


def test_committed_predictions_are_zero_of_six() -> None:
    path = ROOT / "data" / "dataset" / "train_public_pred.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 6
    assert all(row["gold_positive"] is True for row in rows)
    assert all(row["predicted_positive"] is False for row in rows)
