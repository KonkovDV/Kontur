"""Счёт публичного gold. Пустой ответ остаётся 0/6 и не берёт порог."""

from __future__ import annotations

import json
from pathlib import Path

from kontur.cli.score import score_directory, score_scope


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


def test_location_match_does_not_invent_gold_rooms(tmp_path: Path) -> None:
    submission = {
        "object_id": "OBJ-TYUMENSKAYA-5-GOLD-SEED",
        "checks": [
            {
                "parameter_code": "IOS4-078",
                "location": "помещение 140",
                "violation_label": "VIOLATION_PRESENT",
                "evidence": [{"stage": "PD", "file_id": "f-pd", "pdf_page_number": 1}],
            }
        ],
    }
    (tmp_path / "submission_gold.json").write_text(
        json.dumps(submission, ensure_ascii=False),
        encoding="utf-8",
    )
    report = score_directory(tmp_path, match="location")
    assert report["location_in_gold"] is False
    assert report["match"] == "object_id+parameter_code+location"
    matrix = report["matrix"]
    assert isinstance(matrix, dict)
    assert matrix["n_positive"] == 0
    assert matrix["hits"] == 0
    assert matrix["unscored_without_location"] == 6
    code = score_directory(tmp_path)
    code_matrix = code["matrix"]
    assert isinstance(code_matrix, dict)
    assert code_matrix["hits"] == 5


def test_location_match_hits_only_the_same_room() -> None:
    row = {
        "object_id": "OBJ-X",
        "parameter_code": "IOS4-078",
        "violation_label": "VIOLATION_PRESENT",
        "matrix_scope": "MATRIX",
        "location": "помещение 140",
    }
    other = {
        "object_id": "OBJ-X",
        "parameter_code": "IOS4-078",
        "violation_label": "NO_VIOLATION",
        "matrix_scope": "MATRIX",
        "location": "помещение 142",
    }
    submissions = [
        {
            "object_id": "OBJ-X",
            "checks": [
                {
                    "parameter_code": "IOS4-078",
                    "location": "помещение 140",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"file_id": "f", "pdf_page_number": 2}],
                },
                {
                    "parameter_code": "IOS4-078",
                    "location": "помещение 199",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"file_id": "f", "pdf_page_number": 3}],
                },
            ],
        }
    ]
    from kontur.cli.score import _predictions_by_location

    block = score_scope(
        [row, other],
        _predictions_by_location(submissions),
        submissions,
        by_location=True,
    )
    assert block["n_positive"] == 1
    assert block["hits"] == 1
    assert block["false_positives"] == 0
    assert block["unscored_without_location"] == 0
