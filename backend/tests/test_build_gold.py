"""Сгенерированный эталон совпадает с открытым JSONL. Ручная правка не проходит."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from kontur.evaluation.build_gold import (
    OUTPUT_REL,
    SOURCE_REL,
    GoldBuildError,
    build_records,
    check,
    repo_root,
    scoring_row,
    write,
)
from kontur.evaluation.dataset_package import load_gold_inventory
from kontur.evaluation.inventory import QuarantineViolation


def _copy_source(root: Path) -> None:
    source = repo_root() / SOURCE_REL
    target = root / SOURCE_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def test_committed_gold_matches_the_generator() -> None:
    assert check(repo_root()) == []
    records = build_records(repo_root() / SOURCE_REL)
    assert len(records) == 15
    assert all(item["blind"] is False for item in records)
    digest = records[0]["_source_sha256"]
    assert all(item["_source_sha256"] == digest for item in records)
    assert sum(item.get("fpr_denominator") is True for item in records) == 5


def test_inventory_scoring_fields_follow_the_generator() -> None:
    records = build_records(repo_root() / SOURCE_REL)
    inventory = load_gold_inventory()
    checks = inventory["public_gold_checks"]
    assert isinstance(checks, dict)
    rows = checks["rows"]
    assert isinstance(rows, list)
    assert len(rows) == len(records)
    for record, row in zip(records, rows, strict=True):
        assert isinstance(row, dict)
        projected = scoring_row(record)
        for key, value in projected.items():
            assert row[key] == value


def test_check_rejects_a_hand_edit(tmp_path: Path) -> None:
    _copy_source(tmp_path)
    written = write(tmp_path)
    text = written.read_text(encoding="utf-8")
    written.write_text(text.replace("TRAIN-0001", "TRAIN-9999", 1), encoding="utf-8")
    assert check(tmp_path) == [OUTPUT_REL.as_posix()]


def test_sealed_object_is_refused(tmp_path: Path) -> None:
    source = tmp_path / SOURCE_REL
    source.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "check_id": "TRAIN-0001",
        "object_id": "OBJ-RECHNIKOV-7-7",
        "violation_label": "VIOLATION_PRESENT",
    }
    source.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(GoldBuildError, match="не из открытого train"):
        build_records(source)


def test_quarantine_path_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "test_hidden" / SOURCE_REL.name
    source.parent.mkdir(parents=True)
    source.write_text("{}\n", encoding="utf-8")
    with pytest.raises(QuarantineViolation):
        build_records(source)
