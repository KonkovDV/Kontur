"""Счёт публичного gold. Пустой ответ остаётся 0/6 и не берёт порог."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kontur.cli.score import (
    _line,
    _ScoreRow,
    cluster_f1_interval,
    score_directory,
    score_scope,
    score_supplied,
)


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
    report = score_directory(tmp_path, match="code")
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
    assert fpr["n"] == 5
    assert matrix["false_positives"] == 0
    assert matrix["tz_fpr_met"] is False
    default = score_directory(tmp_path)
    assert default["match"] == "object_id+parameter_code+location"
    default_matrix = default["matrix"]
    assert isinstance(default_matrix, dict)
    assert default_matrix["hits"] == 0


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
    assert report["location_in_gold"] is True
    assert report["match"] == "object_id+parameter_code+location"
    matrix = report["matrix"]
    assert isinstance(matrix, dict)
    assert matrix["n_positive"] == 6
    assert matrix["hits"] == 0
    assert matrix["unscored_without_location"] == 0
    code = score_directory(tmp_path, match="code")
    code_matrix = code["matrix"]
    assert isinstance(code_matrix, dict)
    assert code_matrix["hits"] == 5


def test_inventory_room_key_hits_one_row_and_not_the_threshold(tmp_path: Path) -> None:
    submission = {
        "object_id": "OBJ-TYUMENSKAYA-5-GOLD-SEED",
        "checks": [
            {
                "parameter_code": "IOS4-078",
                "location": "140",
                "violation_label": "VIOLATION_PRESENT",
                "evidence": [{"stage": "PD", "file_id": "F0171", "pdf_page_number": 88}],
            }
        ],
    }
    (tmp_path / "submission_gold.json").write_text(
        json.dumps(submission, ensure_ascii=False),
        encoding="utf-8",
    )
    report = score_directory(tmp_path, match="location")
    matrix = report["matrix"]
    assert isinstance(matrix, dict)
    assert matrix["hits"] == 1
    assert matrix["n_positive"] == 6
    assert matrix["tz_recall_met"] is False
    assert report["closes_gate_j"] is False


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


def _positive(
    polygon: list[list[float]] | None,
    *,
    file_id: str | None = "f-rd",
    page: int | None = 1,
) -> dict[str, object]:
    row: dict[str, object] = {
        "object_id": "OBJ-X",
        "parameter_code": "AR-041",
        "violation_label": "VIOLATION_PRESENT",
        "matrix_scope": "MATRIX",
    }
    if polygon is not None:
        row["polygon_norm"] = polygon
    if file_id is not None:
        row["file_id"] = file_id
    if page is not None:
        row["pdf_page_number"] = page
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


def test_same_polygon_on_another_page_is_not_a_localization() -> None:
    from kontur.cli.score import _predictions

    other = _submission(_SQUARE)
    evidence = other[0]["checks"][0]["evidence"][0]
    assert isinstance(evidence, dict)
    evidence["pdf_page_number"] = 12
    block = score_scope([_positive(_SQUARE)], _predictions(other), other)
    assert block["hits"] == 1
    assert block["localized_hits"] == 0
    assert block["localization_unscored"] == 0


def test_polygon_without_file_and_page_is_unscored() -> None:
    from kontur.cli.score import _predictions

    submissions = _submission(_SQUARE)
    block = score_scope(
        [_positive(_SQUARE, file_id=None, page=None)],
        _predictions(submissions),
        submissions,
    )
    assert block["localized_hits"] == 0
    assert block["localization_unscored"] == 1


def test_point_f1_matches_the_bootstrap_counts() -> None:
    from kontur.cli.score import _confusion, _f1_of, _predictions

    rows = [
        {
            "object_id": "OBJ-1",
            "parameter_code": "AR-041",
            "violation_label": "VIOLATION_PRESENT",
            "matrix_scope": "MATRIX",
        },
        {
            "object_id": "OBJ-1",
            "parameter_code": "AR-041",
            "violation_label": "VIOLATION_PRESENT",
            "matrix_scope": "MATRIX",
        },
        {
            "object_id": "OBJ-1",
            "parameter_code": "AR-042",
            "violation_label": "NO_VIOLATION",
            "matrix_scope": "MATRIX",
        },
    ]
    submissions = [
        {
            "object_id": "OBJ-1",
            "checks": [
                {
                    "parameter_code": "AR-041",
                    "location": "объект",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"stage": "RD", "file_id": "f", "pdf_page_number": 1}],
                },
                {
                    "parameter_code": "AR-042",
                    "location": "объект",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"stage": "RD", "file_id": "f", "pdf_page_number": 1}],
                },
            ],
        }
    ]
    block = score_scope(rows, _predictions(submissions), submissions)
    counted = [
        _ScoreRow(object_id="OBJ-1", gold_positive=True, predicted_positive=True),
        _ScoreRow(object_id="OBJ-1", gold_positive=True, predicted_positive=True),
        _ScoreRow(object_id="OBJ-1", gold_positive=False, predicted_positive=True),
    ]
    assert block["f1_point"] == _f1_of(counted)
    true_positive, false_positive, _false_negative = _confusion(counted)
    precision = block["precision"]
    assert isinstance(precision, dict)
    assert precision["n"] == true_positive + false_positive
    assert precision["point"] == true_positive / (true_positive + false_positive)


def test_nan_polygon_is_not_a_localization() -> None:
    """RT-2609-28: NaN в ответе не локализация и не выпадает из знаменателя эталона."""

    from kontur.cli.score import _predictions

    poisoned = [[0.0, 0.0], [1.0, 0.0], [float("nan"), 1.0], [0.0, 1.0]]
    submission = _submission(poisoned)
    block = score_scope([_positive(_SQUARE)], _predictions(submission), submission)
    assert block["hits"] == 1
    assert block["localized_hits"] == 0
    assert block["localization_unscored"] == 0


def test_zero_negatives_are_not_printed_as_zero_fpr() -> None:
    block = score_scope([_positive(None)], {}, [])
    fpr = block["fpr"]
    assert isinstance(fpr, dict)
    assert fpr["n"] == 0
    assert fpr["defined"] is False
    assert fpr["point"] is None
    assert fpr["low"] is None
    assert block["fpr_composition"] == []
    assert block["acceptance_rule"] == "wilson_bound"
    missing = block["not_measured"]
    assert isinstance(missing, list)
    assert "false_positive_rate" in missing
    assert "NO_VIOLATION" in str(block["fpr_denominator_name"])
    tail = _line("MATRIX", block).split("FPR", 1)[1]
    assert "не измерен (n=0)" in tail
    assert "не_измерено=" in tail
    assert "0.000" not in tail


def test_invalid_submission_does_not_receive_a_score(tmp_path: Path) -> None:
    (tmp_path / "submission_bad.json").write_text(
        json.dumps({"object_id": "OBJ-X", "checks": [{"parameter_code": "IOS4-078"}]}),
        encoding="utf-8",
    )
    try:
        score_directory(tmp_path)
    except ValueError as exc:
        assert "submission_bad.json" in str(exc)
    else:
        raise AssertionError("невалидный ответ получил отчёт")


def _supplied_submission(object_id: str, code: str, location: str) -> dict[str, object]:
    return {
        "object_id": object_id,
        "checks": [
            {
                "parameter_code": code,
                "location": location,
                "violation_label": "VIOLATION_PRESENT",
                "evidence": [{"stage": "PD", "file_id": "f", "pdf_page_number": 1}],
            }
        ],
    }


def test_supplied_gold_is_not_stored_and_does_not_close_the_gate() -> None:
    rows = [
        {
            "object_id": "OBJ-CALLER",
            "parameter_code": "PZ-001",
            "violation_label": "VIOLATION_PRESENT",
            "matrix_scope": "MATRIX",
            "score_eligible": True,
            "location": "1",
        }
        for _ in range(40)
    ]
    report = score_supplied(rows, [_supplied_submission("OBJ-CALLER", "PZ-001", "1")])
    assert report["stored"] is False
    assert report["publishes_metrics"] is False
    assert report["closes_gate_j"] is False
    assert report["corpus"] == "request"
    matrix = report["matrix"]
    assert isinstance(matrix, dict)
    assert matrix["hits"] == 40
    assert matrix["tz_recall_met"] is True
    gaps = report["not_measured"]
    assert isinstance(gaps, dict)
    matrix_gaps = gaps["matrix"]
    assert isinstance(matrix_gaps, list)
    assert "false_positive_rate" in matrix_gaps


def test_supplied_score_rejects_an_empty_reference_and_a_bad_submission() -> None:
    try:
        score_supplied([], [])
    except ValueError as exc:
        assert "нет строк эталона" in str(exc)
    else:
        raise AssertionError("пустой эталон получил счёт")
    row = {
        "object_id": "OBJ-CALLER",
        "parameter_code": "PZ-001",
        "violation_label": "VIOLATION_PRESENT",
        "matrix_scope": "MATRIX",
        "score_eligible": True,
        "location": "1",
    }
    try:
        score_supplied([row], [{"object_id": "OBJ-CALLER"}])
    except ValueError as exc:
        assert "submissions[1]" in str(exc)
    else:
        raise AssertionError("ответ без проверки получил счёт")


def test_ineligible_negative_is_not_a_false_positive() -> None:
    from kontur.cli.score import _predictions

    row = {
        "object_id": "OBJ-NOVOSLOBODSKAYA",
        "parameter_code": "KR-055",
        "violation_label": "NO_VIOLATION",
        "matrix_scope": "MATRIX",
        "score_eligible": False,
        "location": "Стена в грунте",
    }
    submissions = [
        {
            "object_id": "OBJ-NOVOSLOBODSKAYA",
            "checks": [
                {
                    "parameter_code": "KR-055",
                    "location": "Стена в грунте",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"stage": "PD", "file_id": "f", "pdf_page_number": 1}],
                }
            ],
        }
    ]
    block = score_scope([row], _predictions(submissions), submissions)
    assert block["n_negative"] == 0
    assert block["false_positives"] == 0
    assert block["unlabeled_positive"] == 1
    fpr = block["fpr"]
    assert isinstance(fpr, dict)
    assert fpr["defined"] is False


def test_second_review_negatives_enter_fpr_and_do_not_meet_the_threshold() -> None:
    from kontur.cli.score import _predictions

    codes = ("PZ-009", "KR-055", "KR-055", "KR-055", "KR-058")
    locations = (
        "Отметка 0.000",
        "Стена в грунте",
        "Фундаментная плита",
        "Вертикальные конструкции подземной части",
        "Фундаментная плита",
    )
    rows = [
        {
            "object_id": "OBJ-NOVOSLOBODSKAYA",
            "parameter_code": code,
            "violation_label": "NO_VIOLATION",
            "matrix_scope": "MATRIX",
            "score_eligible": False,
            "fpr_denominator": True,
            "location": location,
        }
        for code, location in zip(codes, locations, strict=True)
    ]
    quiet = score_scope(rows, {}, [])
    assert quiet["n_positive"] == 0
    assert quiet["n_negative"] == 5
    assert quiet["false_positives"] == 0
    assert quiet["tz_fpr_met"] is False
    composition = quiet["fpr_composition"]
    assert isinstance(composition, list)
    assert composition == sorted(composition)
    assert len(composition) == 5
    assert "OBJ-NOVOSLOBODSKAYA | PZ-009" in composition
    assert composition.count("OBJ-NOVOSLOBODSKAYA | KR-055") == 3
    submissions = [
        {
            "object_id": "OBJ-NOVOSLOBODSKAYA",
            "checks": [
                {
                    "parameter_code": "PZ-009",
                    "location": "Отметка 0.000",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"stage": "PD", "file_id": "f", "pdf_page_number": 1}],
                }
            ],
        }
    ]
    fired = score_scope(rows, _predictions(submissions), submissions)
    assert fired["false_positives"] == 1
    assert fired["tz_fpr_met"] is False


def test_other_row_page_is_not_a_localization() -> None:
    from kontur.cli.score import _predictions_by_location

    own = {
        "object_id": "OBJ-X",
        "parameter_code": "IOS4-078",
        "violation_label": "VIOLATION_PRESENT",
        "matrix_scope": "MATRIX",
        "location": "140",
        "evidence": [
            {"file_id": "F0171", "pdf_page_number": 88, "polygon_norm": _SQUARE},
            {"file_id": "F0201", "pdf_page_number": 18, "polygon_norm": _SQUARE},
        ],
    }
    other = {
        "object_id": "OBJ-X",
        "parameter_code": "IOS4-079",
        "violation_label": "VIOLATION_PRESENT",
        "matrix_scope": "MATRIX",
        "location": "012",
        "evidence": [
            {"file_id": "F0171", "pdf_page_number": 104, "polygon_norm": _SQUARE},
            {"file_id": "F0201", "pdf_page_number": 17, "polygon_norm": _SQUARE},
        ],
    }
    submissions = [
        {
            "object_id": "OBJ-X",
            "checks": [
                {
                    "parameter_code": "IOS4-078",
                    "location": "140",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [
                        {
                            "stage": "RD",
                            "file_id": "F0201",
                            "pdf_page_number": 17,
                            "polygon_norm": _SQUARE,
                        }
                    ],
                }
            ],
        }
    ]
    block = score_scope(
        [own, other],
        _predictions_by_location(submissions),
        submissions,
        by_location=True,
    )
    assert block["hits"] == 1
    assert block["localized_hits"] == 0
    assert block["localization_unscored"] == 0


def test_three_fpr_names_do_not_share_one_denominator() -> None:
    from kontur.cli.score import _predictions

    tz_row = {
        "object_id": "OBJ-N",
        "parameter_code": "KR-055",
        "violation_label": "NO_VIOLATION",
        "score_eligible": False,
        "fpr_denominator": True,
        "location": "Стена",
    }
    gate_row = {
        "object_id": "OBJ-N",
        "parameter_code": "KR-058",
        "violation_label": "NO_VIOLATION",
        "score_eligible": True,
        "location": "Плита",
    }
    outside = {
        "object_id": "OBJ-N",
        "parameter_code": "PZ-009",
        "violation_label": "NO_VIOLATION",
        "score_eligible": False,
        "location": "Отметка",
    }
    block = score_scope([tz_row, gate_row, outside], _predictions([]), [])
    sets = block["fpr_sets"]
    assert isinstance(sets, dict)
    tz = sets["FPR_ТЗ"]
    gate = sets["FPR_ворот"]
    extended = sets["FPR_расш"]
    assert isinstance(tz, dict) and isinstance(gate, dict) and isinstance(extended, dict)
    assert tz["n"] == 2
    assert tz["decides_threshold"] is True
    assert gate["n"] == 1
    assert gate["decides_threshold"] is False
    assert extended["n"] == 3
    assert extended["decides_threshold"] is False
    assert block["tz_fpr_met"] is False


def test_named_hit_without_confirmation_fails_the_approved_level() -> None:
    from kontur.cli.score import _predictions

    row = {
        "object_id": "OBJ-A",
        "parameter_code": "PZ-001",
        "violation_label": "VIOLATION_PRESENT",
        "score_eligible": True,
        "location": "1",
    }
    submission = [
        {
            "object_id": "OBJ-A",
            "checks": [
                {
                    "parameter_code": "PZ-001",
                    "location": "1",
                    "violation_label": "VIOLATION_PRESENT",
                    "evidence": [{"stage": "PD", "file_id": "f", "pdf_page_number": 1}],
                }
            ],
        }
    ]
    block = score_scope([row], _predictions(submission), submission)
    levels = block["levels"]
    assert isinstance(levels, dict)
    named = levels["named"]
    approved = levels["approved"]
    assert isinstance(named, dict) and isinstance(approved, dict)
    assert named["tp"] == 1
    assert named["decides_gate_j"] is False
    assert approved["tp"] == 0
    assert approved["fp"] == 1
    assert approved["decides_gate_j"] is True
    assert approved["tz_recall_met"] is False
    assert block["tz_recall_met"] is False
    assert "sensitivity" in block["not_measured"]


def test_source_verified_localization_does_not_move_the_strict_count() -> None:
    from kontur.cli.score import _predictions_by_location

    strict = [[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1]]
    other = [[0.5, 0.5], [1.0, 0.5], [1.0, 1.0], [0.5, 1.0]]
    row = {
        "object_id": "OBJ-X",
        "parameter_code": "IOS4-078",
        "violation_label": "VIOLATION_PRESENT",
        "location": "140",
        "evidence": [{"file_id": "F1", "pdf_page_number": 2, "polygon_norm": strict}],
        "localization_adjudication": {
            "reason": "POSSIBLE_GOLD_LOCALIZATION_CONFLICT",
            "file_id": "F1",
            "pdf_page_number": 2,
            "polygon_norm": other,
        },
    }
    submission = [
        {
            "object_id": "OBJ-X",
            "checks": [
                {
                    "parameter_code": "IOS4-078",
                    "location": "140",
                    "violation_label": "VIOLATION_PRESENT",
                    "confidence": 0.95,
                    "evidence": [
                        {
                            "stage": "PD",
                            "file_id": "F1",
                            "pdf_page_number": 2,
                            "polygon_norm": other,
                        }
                    ],
                }
            ],
        }
    ]
    block = score_scope(
        [row],
        _predictions_by_location(submission),
        submission,
        by_location=True,
    )
    assert block["localized_hits"] == 0
    verified = block["localization_source_verified"]
    assert isinstance(verified, dict)
    assert verified["n"] == 1
    assert verified["point"] == pytest.approx(1.0)
    sensitivity = block["sensitivity"]
    assert isinstance(sensitivity, dict)
    assert sensitivity["decides_threshold"] is False
    assert sensitivity["n_claims"] == 1


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
