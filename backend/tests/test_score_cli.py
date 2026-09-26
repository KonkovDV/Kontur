"""Счёт публичного gold. Пустой ответ остаётся 0/6 и не берёт порог."""

from __future__ import annotations

import json
from pathlib import Path

from kontur.cli.score import _line, _ScoreRow, cluster_f1_interval, score_directory, score_scope


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
    assert matrix["localized_hits"] == 0
    assert matrix["localization_unscored"] == 6
    assert matrix["f1_interval"] is None
    assert matrix["tz_recall_met"] is False
    fpr = matrix["fpr"]
    assert isinstance(fpr, dict)
    assert fpr["defined"] is True


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


_SQUARE = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
_CORNER = [[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]]


def _positive(polygon: list[list[float]] | None) -> dict[str, object]:
    row: dict[str, object] = {
        "object_id": "OBJ-X",
        "parameter_code": "AR-041",
        "violation_label": "VIOLATION_PRESENT",
        "matrix_scope": "MATRIX",
    }
    if polygon is not None:
        row["polygon_norm"] = polygon
    return row


def _submission(polygon: list[list[float]] | None) -> list[dict[str, object]]:
    evidence: dict[str, object] = {"stage": "RD", "file_id": "f-rd", "pdf_page_number": 1}
    if polygon is not None:
        evidence["polygon_norm"] = polygon
    return [
        {
            "object_id": "OBJ-X",
            "checks": [
                {
                    "parameter_code": "AR-041",
                    "location": "объект",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [evidence],
                }
            ],
        }
    ]


def test_page_number_without_polygon_is_not_a_localization() -> None:
    from kontur.cli.score import _predictions

    submissions = _submission(None)
    block = score_scope([_positive(None)], _predictions(submissions), submissions)
    assert block["hits"] == 1
    assert block["localized_hits"] == 0
    assert block["localization_unscored"] == 1


def test_same_polygon_localizes_and_a_corner_does_not() -> None:
    from kontur.cli.score import _predictions

    same = _submission(_SQUARE)
    hit = score_scope([_positive(_SQUARE)], _predictions(same), same)
    assert hit["localized_hits"] == 1
    assert hit["localization_unscored"] == 0
    miss = _submission(_CORNER)
    missed = score_scope([_positive(_SQUARE)], _predictions(miss), miss)
    assert missed["hits"] == 1
    assert missed["localized_hits"] == 0
    assert missed["localization_unscored"] == 0


def test_zero_negatives_are_not_printed_as_zero_fpr() -> None:
    block = score_scope([_positive(None)], {}, [])
    fpr = block["fpr"]
    assert isinstance(fpr, dict)
    assert fpr["n"] == 0
    assert fpr["defined"] is False
    assert fpr["point"] == 0.0
    tail = _line("MATRIX", block).split("FPR", 1)[1]
    assert "не определён (n=0)" in tail
    assert "0.000" not in tail


def test_f1_interval_is_withheld_below_ten_clusters() -> None:
    few = [
        _ScoreRow(object_id=f"OBJ-{index}", gold_positive=True, predicted_positive=True)
        for index in range(9)
    ]
    assert cluster_f1_interval(few) is None
    many = [
        _ScoreRow(object_id=f"OBJ-{index}", gold_positive=True, predicted_positive=True)
        for index in range(12)
    ]
    assert cluster_f1_interval(many, draws=40) == (1.0, 1.0)
