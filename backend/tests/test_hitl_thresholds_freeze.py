"""Заморозка hitl_thresholds.v1.json: sha256 и зеркало web совпадают."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "calibration" / "hitl_thresholds.v1.json"
WEB = ROOT / "web" / "src" / "config" / "hitl_thresholds.v1.json"
SHA = ROOT / "data" / "calibration" / "hitl_thresholds.v1.sha256"


def test_thresholds_are_uncalibrated_placeholder() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    assert payload["schema"] == "kontur.hitl_thresholds.v1"
    assert payload["calibrated"] is False
    assert payload["t_high"] is None
    assert payload["t_low"] is None
    assert payload["closes_gate_i"] is False
    assert payload["gold"] is False
    assert payload["insufficient_data"] is True
    assert payload["ui_fallback"]["t_high"] == 0.9
    assert payload["ui_fallback"]["t_low"] == 0.7
    assert "не калибр" in payload["ui_fallback"]["label_suffix"]


def test_sha256_matches_committed_digest() -> None:
    raw = DATA.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    recorded = SHA.read_text(encoding="utf-8").split()[0]
    assert digest == recorded


def test_web_mirror_byte_identical() -> None:
    assert DATA.read_bytes() == WEB.read_bytes()
