"""Обратные if/then схемы находки: ложное нарушение не проходит валидацию."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "finding.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _base(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "finding_id": "f-1",
        "rule_code": "PZ-001",
        "finding_status": "CANDIDATE",
        "review_priority": "HIGH",
        "evidence_group_id": "eg-1",
        "versions": {
            "matrix_version": "draft-0",
            "rule_version": "0.1.0",
            "model_version": "none",
        },
    }
    payload.update(overrides)
    return payload


def test_candidate_cannot_count_as_violation() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_base(counts_as_violation=True), SCHEMA)


def test_confirmed_requires_counts_as_violation() -> None:
    payload = _base(
        finding_status="CONFIRMED_VIOLATION",
        inspector_decision={
            "inspector_id": "i-1",
            "action": "CONFIRM",
            "timestamp": "2026-09-16T12:00:00Z",
            "comment": "подтверждаю",
        },
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


def test_confirmed_rejects_clarification_action() -> None:
    payload = _base(
        finding_status="CONFIRMED_VIOLATION",
        counts_as_violation=True,
        inspector_decision={
            "inspector_id": "i-1",
            "action": "REQUEST_CLARIFICATION",
            "timestamp": "2026-09-16T12:00:00Z",
            "comment": "уточнить",
        },
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


def test_negative_requires_reason_and_comment() -> None:
    payload = _base(
        finding_status="NEGATIVE_VERIFIED",
        inspector_decision={
            "inspector_id": "i-1",
            "action": "REJECT",
            "timestamp": "2026-09-16T12:00:00Z",
            "reason_code": None,
            "comment": None,
        },
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


def test_valid_confirmed_violation_passes() -> None:
    jsonschema.validate(
        _base(
            finding_status="CONFIRMED_VIOLATION",
            counts_as_violation=True,
            inspector_decision={
                "inspector_id": "i-1",
                "action": "CONFIRM",
                "timestamp": "2026-09-16T12:00:00Z",
                "comment": "Расхождение по площади застройки.",
            },
        ),
        SCHEMA,
    )
