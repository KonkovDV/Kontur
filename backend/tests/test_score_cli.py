"""Счёт публичного gold. Пустой ответ остаётся 0/6 и не берёт порог."""

from __future__ import annotations

import json
from pathlib import Path

from kontur.cli.score import score_directory


def test_empty_submissions_stay_zero_of_six(tmp_path: Path) -> None:
    report = score_directory(tmp_path)
    matrix = report["matrix"]
    assert isinstance(matrix, dict)
    assert report["closes_gate_j"] is False
    assert matrix["n_positive"] == 6
    assert matrix["hits"] == 0
    assert matrix["tz_recall_met"] is False
    recall = matrix["recall"]
    assert isinstance(recall, dict)
    assert recall["n"] == 6
    assert recall["low"] == 0.0
    free = report["free_search"]
    assert isinstance(free, dict)
    assert free["n_positive"] == 4
    assert free["hits"] == 0


def test_one_code_hits_every_duplicate_row_and_does_not_meet_tz(tmp_path: Path) -> None:
    submission = {
        "object_id": "OBJ-TYUMENSKAYA-5-GOLD-SEED",
        "checks": [
            {
                "parameter_code": "IOS4-078",
                "location": "объект",
                "violation_label": "VIOLATION_PRESENT",
                "evidence": [{"stage": "PD", "file_id": "f-pd", "pdf_page_number": 1}],
            }
        ],
    }
    (tmp_path / "submission_gold.json").write_text(
        json.dumps(submission, ensure_ascii=False),
        encoding="utf-8",
    )
    report = score_directory(tmp_path)
    matrix = report["matrix"]
    assert isinstance(matrix, dict)
    assert matrix["hits"] == 5
    assert matrix["n_positive"] == 6
    assert matrix["localized_hits"] == 5
    assert matrix["tz_recall_met"] is False
