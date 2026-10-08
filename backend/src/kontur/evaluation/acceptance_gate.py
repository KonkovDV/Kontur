"""Сводка гейтов I/J/K/L. Пустой замер — не сдача.

Три статуса: ok, fail и incomplete.
Правило без выборки не проходит. Это не гейт публикации модели
(`release_gate.evaluate`): тот проверяет подпись и категории.
"""

from __future__ import annotations

from collections.abc import Mapping

STATUS_OK = "ok"
STATUS_BAD = "fail"
STATUS_MISSING = "incomplete"


def _status(present: bool, ok: bool) -> str:
    if not present:
        return STATUS_MISSING
    return STATUS_OK if ok else STATUS_BAD


def _ocr_status(ocr: Mapping[str, object] | None) -> str:
    """SILVER и чужой корпус не судятся. Замеренный GOLD ниже порога — fail."""

    if ocr is None or ocr.get("measured") is not True:
        return STATUS_MISSING
    if ocr.get("closes_gate_i") is True:
        return STATUS_OK
    if ocr.get("gold") is False or ocr.get("silver_not_gold") is True:
        return STATUS_MISSING
    return STATUS_BAD


def _section(evidence: Mapping[str, object], key: str) -> dict[str, object] | None:
    value = evidence.get(key)
    if not isinstance(value, dict):
        return None
    return {str(name): item for name, item in value.items()}


def judge_gates(evidence: Mapping[str, object]) -> dict[str, object]:
    """Свести замеры I/J/K/L. Выпуск закрыт только если все четыре PASS."""

    ocr = _section(evidence, "ocr")
    frozen = _section(evidence, "frozen_val")
    usability = _section(evidence, "usability")
    timings = _section(evidence, "timings")
    rows = {
        "I": _ocr_status(ocr),
        "J": _status(
            frozen is not None and frozen.get("measured") is True,
            bool(frozen and frozen.get("closes_gate_j") is True),
        ),
        "K": _status(
            usability is not None and usability.get("users") == 5,
            bool(usability and usability.get("closes_gate_k") is True),
        ),
        "L": _status(
            timings is not None and timings.get("measured") is True,
            bool(timings and timings.get("within_limits") is True),
        ),
    }
    if any(item == STATUS_BAD for item in rows.values()):
        verdict = STATUS_BAD
    elif any(item == STATUS_MISSING for item in rows.values()):
        verdict = STATUS_MISSING
    else:
        verdict = STATUS_OK
    return {"verdict": verdict, "gates": rows, "closes_release": verdict == STATUS_OK}
