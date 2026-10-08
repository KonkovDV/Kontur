"""Инструменты замера, как у соседних команд: сессии, OCR и frozen val.

Учебные пять сессий и SILVER порог гейты не закрывают.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kontur.evaluation.frozen_val import FrozenValRow, summarize_frozen_val
from kontur.evaluation.metrics import wilson
from kontur.evaluation.ocr_pilot import judge_recorded_ocr
from kontur.evaluation.usability_audit import audit_event_log, audit_sessions


def _session(participant: str, *, teaching: bool, clicks: int = 2, seconds: int = 600) -> dict:
    return {
        "schema_version": "kontur-usability-v1",
        "participant_id": participant,
        "duration_seconds": seconds,
        "closes_gate_k": False,
        "teaching_data": teaching,
        "decisions": [
            {"finding_id": f"f-{index}", "clicks_to_decision": clicks}
            for index in range(5)
        ],
    }


def test_five_teaching_sessions_do_not_close_gate_k() -> None:
    sessions = [_session(f"u-{index}", teaching=True) for index in range(5)]
    report = audit_sessions(sessions)
    assert report["users"] == 5
    assert report["passed_thresholds"] is True
    assert report["teaching_data"] is True
    assert report["closes_gate_k"] is False


def test_five_observed_sessions_within_limits_close_gate_k() -> None:
    sessions = [_session(f"insp-{index}", teaching=False) for index in range(5)]
    report = audit_sessions(sessions)
    assert report["closes_gate_k"] is True


def test_a_slow_session_keeps_the_gate_open() -> None:
    sessions = [_session(f"insp-{index}", teaching=False) for index in range(5)]
    sessions[0]["duration_seconds"] = 31 * 60
    report = audit_sessions(sessions)
    assert report["passed_thresholds"] is False
    assert report["closes_gate_k"] is False


def _ui_journal(*, users: int, cards: int, teaching: bool) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    start = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)
    cursor = 0
    for user_index in range(users):
        user = f"u-{user_index}"
        for card in range(cards):
            check = f"CHK-{card:04d}"
            moment = start + timedelta(seconds=cursor)
            cursor += 3
            rows.append(
                {
                    "user_id": user,
                    "action": "UI_CLICK",
                    "object_id": "OBJ-1",
                    "timestamp": moment.isoformat(),
                    "details": {
                        "screen": "queue",
                        "target": "open-card",
                        "check_id": check,
                        "click_index": 1,
                    },
                }
            )
            rows.append(
                {
                    "user_id": user,
                    "action": "UI_CARD_OPEN",
                    "timestamp": (moment + timedelta(milliseconds=400)).isoformat(),
                    "details": {"screen": "card", "check_id": check, "click_index": 1},
                }
            )
            rows.append(
                {
                    "user_id": user,
                    "action": "UI_DECISION_SUBMIT",
                    "timestamp": (moment + timedelta(seconds=2)).isoformat(),
                    "details": {
                        "screen": "card",
                        "target": "decision-CONFIRM",
                        "check_id": check,
                        "click_index": 2,
                        "duration_ms": 2000,
                    },
                }
            )
    return {"teaching_data": teaching, "entries": rows}


def test_a_short_event_log_is_not_measured() -> None:
    report = audit_event_log(_ui_journal(users=3, cards=3, teaching=True))
    assert report["measured"] is False
    assert report["closes_gate_k"] is False


def test_fourteen_cards_do_not_close_gate_k_while_the_log_is_teaching() -> None:
    report = audit_event_log(_ui_journal(users=5, cards=14, teaching=True))
    assert report["measured"] is True
    assert report["users"] == 5
    assert report["passed_thresholds"] is True
    assert report["closes_gate_k"] is False


def test_an_observed_fourteen_card_log_can_close_gate_k() -> None:
    report = audit_event_log(_ui_journal(users=5, cards=14, teaching=False))
    assert report["closes_gate_k"] is True
    assert report["max_clicks"] == 2


def test_silver_ocr_does_not_close_gate_i_even_when_the_bound_is_high() -> None:
    perfect = wilson(100, 100)
    silver = judge_recorded_ocr(perfect, gold=False)
    gold = judge_recorded_ocr(perfect, gold=True)
    weak = judge_recorded_ocr(wilson(1, 100), gold=True)
    assert silver["threshold_met"] is True
    assert silver["closes_gate_i"] is False
    assert gold["closes_gate_i"] is True
    assert weak["closes_gate_i"] is False


def test_missing_frozen_val_is_not_a_closed_gate() -> None:
    report = summarize_frozen_val(None)
    assert report["measured"] is False
    assert report["closes_gate_j"] is False


def test_frozen_val_closes_when_every_section_meets_the_bound() -> None:
    rows = [
        FrozenValRow("OBJ-A", "PZ-001", True, True),
        FrozenValRow("OBJ-B", "PZ-001", True, True),
    ] * 20
    met = summarize_frozen_val(rows, sections={"PZ-001": "ПЗ"})
    assert met["closes_gate_j"] is True
    assert met["sections"] == 1
    missed = summarize_frozen_val(
        [FrozenValRow("OBJ-A", "PZ-001", True, False) for _ in range(20)],
        sections={"PZ-001": "ПЗ"},
    )
    assert missed["closes_gate_j"] is False


def test_a_weak_rule_does_not_block_a_section_that_meets_the_bound() -> None:
    """20/20 и 18/20 по отдельности: второе правило ниже 0,80, раздел 38/40 — выше."""

    sections = {"PZ-001": "ПЗ", "PZ-002": "ПЗ", "KR-010": "КР"}
    strong = [FrozenValRow("OBJ-A", "PZ-001", True, True) for _ in range(20)]
    weak = [FrozenValRow("OBJ-A", "PZ-002", True, True) for _ in range(18)]
    weak.append(FrozenValRow("OBJ-A", "PZ-002", True, False))
    weak.append(FrozenValRow("OBJ-B", "PZ-002", True, False))
    together = summarize_frozen_val([*strong, *weak], sections=sections)
    assert together["rules_meeting_wilson_lower_bound"] == 1
    assert together["closes_gate_j"] is True
    other = [FrozenValRow("OBJ-C", "KR-010", True, True) for _ in range(6)]
    blocked = summarize_frozen_val([*strong, *weak, *other], sections=sections)
    assert blocked["closes_gate_j"] is False
    by_section = blocked["by_section"]
    assert isinstance(by_section, dict)
    assert by_section["КР"]["meets"] is False
