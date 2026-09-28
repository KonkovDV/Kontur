"""Примеры JSON в пакете сдачи проходят схемы и не отдают вердикт автомата."""

from __future__ import annotations

import json

from kontur.cli.run_package import _schema_validator
from kontur.evaluation.agent_dumps import repo_root

_EXAMPLES = repo_root() / "submission" / "05-additional" / "examples"
_DEMO_CODES = {"PZ-001", "KR-055", "AR-041"}


def _load(case: str, name: str) -> dict[str, object]:
    payload = json.loads((_EXAMPLES / case / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{case}/{name}: ожидался объект")
    return payload


def _checks(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload["checks"]
    if not isinstance(raw, list):
        raise AssertionError("checks не список")
    return [item for item in raw if isinstance(item, dict)]


def _blob(case: str) -> str:
    folder = _EXAMPLES / case
    return (folder / "submission.json").read_text(encoding="utf-8") + (
        folder / "protocol.json"
    ).read_text(encoding="utf-8")


def test_unattended_example_is_schema_valid_and_refuses() -> None:
    submission = _load("unattended", "submission.json")
    protocol = _load("unattended", "protocol.json")
    _schema_validator("submission.schema.json").validate(submission)
    _schema_validator("protocol.schema.json").validate(protocol)
    checks = _checks(submission)
    assert len(checks) == 132
    assert {item["violation_label"] for item in checks} == {"COMPARISON_IMPOSSIBLE"}
    assert protocol["violation_count"] == 0
    blob = _blob("unattended")
    assert "CONFIRMED_VIOLATION" not in blob
    assert "AUTO_NO_DIFFERENCE" not in blob


def test_after_select_example_has_three_candidates_with_evidence() -> None:
    submission = _load("after_etalon_select", "submission.json")
    protocol = _load("after_etalon_select", "protocol.json")
    _schema_validator("submission.schema.json").validate(submission)
    _schema_validator("protocol.schema.json").validate(protocol)
    checks = _checks(submission)
    assert len(checks) == 132
    present = [item for item in checks if item["violation_label"] == "VIOLATION_PRESENT"]
    assert {str(item["parameter_code"]) for item in present} == _DEMO_CODES
    for item in present:
        evidence = item["evidence"]
        assert isinstance(evidence, list)
        assert {row["stage"] for row in evidence if isinstance(row, dict)} == {"PD", "RD"}
        assert {row["file_id"] for row in evidence if isinstance(row, dict)} == {"f-pd", "f-rd"}
    sections = protocol["sections"]
    assert isinstance(sections, dict)
    candidates = sections["candidates"]
    assert isinstance(candidates, list) and len(candidates) == 3
    assert sections["confirmed"] == []
    assert protocol["violation_count"] == 0
    blob = _blob("after_etalon_select")
    assert "CONFIRMED_VIOLATION" not in blob
    assert "AUTO_NO_DIFFERENCE" not in blob
