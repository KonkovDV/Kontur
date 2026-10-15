"""Сводка юзабилити по JSON рекордера. Пять учебных сессий гейт не закрывают.

Формат строки — `kontur-usability-v1` из экрана инспектора. Пороги ТЗ:
не больше 30 минут на протокол и не больше 3 кликов на находку.
`closes_gate_k` становится true только когда все пять сессий помечены
`teaching_data: false` и пороги взяты. Учебный комплект этого не делает.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

REQUIRED_SESSIONS = 5
MAX_CLICKS = 3
MAX_SECONDS = 30 * 60
MIN_CARDS = 14
CARD_OPEN_DEDUPE_MS = 5000
_ACTION_EVENTS = frozenset({"CLICK", "HOTKEY", "CARD_OPEN", "DECISION_SUBMIT"})


class _UiEvent(TypedDict):
    event: str
    user: str
    object_id: object
    check_id: object
    screen: object
    target: object
    click_index: int | None
    duration_ms: int | None
    ts: int


def _plain_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} должен быть целым")
    return value


def audit_sessions(sessions: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Посчитать пять сессий. Меньше пяти — замер не состоялся."""

    if len(sessions) != REQUIRED_SESSIONS:
        return {
            "users": len(sessions),
            "required_users": REQUIRED_SESSIONS,
            "passed_thresholds": False,
            "teaching_data": True,
            "closes_gate_k": False,
            "participants": [],
        }
    participants: list[dict[str, object]] = []
    teaching = False
    for session in sessions:
        if session.get("schema_version") != "kontur-usability-v1":
            raise ValueError("ожидался kontur-usability-v1")
        if session.get("closes_gate_k") is not False:
            raise ValueError("файл сессии не имеет права сам закрывать гейт K")
        if session.get("teaching_data") is not False:
            teaching = True
        decisions = session.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            raise ValueError("в сессии нет решений")
        clicks = [
            _plain_int(item.get("clicks_to_decision"), "clicks_to_decision")
            for item in decisions
            if isinstance(item, dict)
        ]
        if not clicks:
            raise ValueError("в сессии нет решений")
        duration = _plain_int(session.get("duration_seconds"), "duration_seconds")
        max_clicks = max(clicks)
        participants.append(
            {
                "participant_id": str(session["participant_id"]),
                "duration_seconds": duration,
                "max_clicks": max_clicks,
                "within_thirty_minutes": duration <= MAX_SECONDS,
                "within_three_clicks": max_clicks <= MAX_CLICKS,
            }
        )
    passed = all(
        item["within_thirty_minutes"] and item["within_three_clicks"] for item in participants
    )
    ids = [str(item["participant_id"]) for item in participants]
    if len(set(ids)) != REQUIRED_SESSIONS:
        passed = False
    return {
        "users": REQUIRED_SESSIONS,
        "required_users": REQUIRED_SESSIONS,
        "passed_thresholds": passed,
        "teaching_data": teaching,
        "closes_gate_k": passed and not teaching,
        "participants": participants,
    }


def _millis(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def _detail_map(row: Mapping[str, object]) -> dict[str, object]:
    raw = row.get("details")
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _normalise_events(rows: Sequence[object]) -> list[_UiEvent]:
    events: list[_UiEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "")
        if not action.startswith("UI_"):
            continue
        details = _detail_map(row)
        stamp = _millis(row.get("timestamp")) or _millis(details.get("client_ts"))
        if stamp is None:
            continue
        events.append(
            {
                "event": action[3:],
                "user": str(row.get("user_id") or ""),
                "object_id": row.get("object_id") or details.get("object_id"),
                "check_id": details.get("check_id"),
                "screen": details.get("screen"),
                "target": details.get("target"),
                "click_index": _optional_int(details.get("click_index")),
                "duration_ms": _optional_int(details.get("duration_ms")),
                "ts": stamp,
            }
        )
    events.sort(key=lambda item: item["ts"])
    return events


def _is_decision_action(event: _UiEvent) -> bool:
    if event.get("event") not in _ACTION_EVENTS:
        return False
    if event.get("click_index") is not None:
        return True
    target = event.get("target")
    return (
        event.get("screen") == "card"
        and isinstance(target, str)
        and target.startswith("decision-")
    )


def _count_actions(card_events: Sequence[_UiEvent]) -> int:
    actions = 0
    previous: _UiEvent | None = None
    for event in card_events:
        if not _is_decision_action(event):
            previous = event
            continue
        mounts_after_click = (
            event["event"] == "CARD_OPEN"
            and previous is not None
            and previous["event"] == "CLICK"
            and previous["screen"] == "queue"
            and previous["check_id"] == event["check_id"]
            and event["ts"] - previous["ts"] <= CARD_OPEN_DEDUPE_MS
        )
        if not mounts_after_click:
            actions += 1
        previous = event
    return actions


def audit_event_log(payload: Mapping[str, object] | Sequence[object]) -> dict[str, object]:
    """Клики и цикл из журнала UI. Мало карточек — «не измерено», не пропуск.

    Пять пользователей закрывают гейт K только если журнал помечен
    `teaching_data: false` и в кейсе не меньше 14 карточек с решением.
    Голый массив событий учебным и считается.
    """

    teaching = True
    rows: Sequence[object]
    if isinstance(payload, Mapping):
        teaching = payload.get("teaching_data") is not False
        raw = payload.get("entries") or payload.get("rows") or payload.get("items")
        if not isinstance(raw, list):
            raise ValueError("в журнале нет entries")
        rows = raw
    else:
        rows = payload
    events = _normalise_events(rows)
    checks = {event["check_id"] for event in events if event["check_id"]}
    by_user: dict[str, dict[str, list[_UiEvent]]] = {}
    span: dict[str, list[int]] = {}
    for event in events:
        user = event["user"]
        stamp = event["ts"]
        span.setdefault(user, [stamp, stamp])
        span[user][0] = min(span[user][0], stamp)
        span[user][1] = max(span[user][1], stamp)
        check_id = event["check_id"]
        if not check_id:
            continue
        cards = by_user.setdefault(user, {})
        cards.setdefault(str(check_id), []).append(event)
    participants: list[dict[str, object]] = []
    action_counts: list[int] = []
    cycles: list[float] = []
    for user in sorted(by_user):
        decided_actions: list[int] = []
        for card_events in by_user[user].values():
            if any(item["event"] == "DECISION_SUBMIT" for item in card_events):
                decided_actions.append(_count_actions(card_events))
        cycle = (span[user][1] - span[user][0]) / 1000
        action_counts.extend(decided_actions)
        cycles.append(cycle)
        participants.append(
            {
                "participant_id": user,
                "cards_decided": len(decided_actions),
                "max_clicks": max(decided_actions) if decided_actions else None,
                "duration_seconds": cycle,
            }
        )
    measured = len(checks) >= MIN_CARDS and bool(action_counts)
    max_clicks = max(action_counts) if action_counts else None
    max_cycle = max(cycles) if cycles else None
    within_clicks = max_clicks is not None and max_clicks <= MAX_CLICKS
    within_time = max_cycle is not None and max_cycle <= MAX_SECONDS
    ids = [str(item["participant_id"]) for item in participants]
    closes = (
        measured
        and not teaching
        and len(set(ids)) == REQUIRED_SESSIONS
        and within_clicks
        and within_time
    )
    reason = None
    if not measured:
        reason = (
            f"карточек в кейсе {len(checks)} < {MIN_CARDS}"
            if len(checks) < MIN_CARDS
            else "нет ни одной карточки с решением"
        )
    return {
        "users": len(set(ids)),
        "required_users": REQUIRED_SESSIONS,
        "cards_in_case": len(checks),
        "min_cards_required": MIN_CARDS,
        "measured": measured,
        "not_measured_reason": reason,
        "passed_thresholds": bool(measured and within_clicks and within_time),
        "teaching_data": teaching,
        "closes_gate_k": closes,
        "max_clicks": max_clicks,
        "max_cycle_seconds": max_cycle,
        "participants": participants,
    }


def ui_journal(
    records: Sequence[tuple[str, str, Mapping[str, object]]],
) -> dict[str, object]:
    """Журнал UI_* для audit_event_log. Учебный: клиент не закрывает гейт K."""

    entries: list[dict[str, object]] = []
    for actor, action, payload in records:
        if not action.startswith("UI_"):
            continue
        entries.append(
            {
                "action": action,
                "user_id": actor,
                "timestamp": str(payload.get("client_ts") or ""),
                "object_id": payload.get("object_id"),
                "details": dict(payload),
            }
        )
    return {"teaching_data": True, "entries": entries}


def load_session_dir(folder: Path) -> tuple[dict[str, object], ...]:
    sessions: list[dict[str, object]] = []
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            sessions.append(payload)
    return tuple(sessions)


def load_audit(path: Path) -> dict[str, object]:
    """Каталог сессий `kontur-usability-v1` или один журнал UI-событий."""

    if path.is_dir():
        return audit_sessions(load_session_dir(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list) or (
        isinstance(payload, dict) and "entries" in payload
    ):
        return audit_event_log(payload)
    if isinstance(payload, dict) and payload.get("schema_version") == "kontur-usability-v1":
        return audit_sessions((payload,))
    raise ValueError("ожидался каталог сессий или журнал UI")


if __name__ == "__main__":
    from kontur.cli.usability_audit import main

    raise SystemExit(main())
