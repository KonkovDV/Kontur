"""Таблица ТЗ п. 11 не превращает пустую строку в пропуск."""

from __future__ import annotations

from kontur.evaluation.tz11 import (
    CLAIMED,
    IN_LIMIT,
    NOT_QUOTABLE,
    OVER,
    UNMEASURED,
    evaluate,
    measure_local,
    timings_evidence,
)


def test_ten_files_of_fifty_megabytes_are_refused_as_one_batch() -> None:
    measured = measure_local()
    upload = measured["1"]
    assert upload["files"] == 10
    assert upload["accepted"] == 0
    results = evaluate(measured)
    row = next(item for item in results if item.row.row_id == "1")
    assert row.verdict == NOT_QUOTABLE
    assert "1" in timings_evidence(results)["over"]


def test_an_accepted_ten_file_upload_can_be_quoted() -> None:
    results = evaluate(
        {"1": {"value": 1.0, "files": 10, "each_bytes": 50 * 1024 * 1024, "accepted": 10}}
    )
    row = next(item for item in results if item.row.row_id == "1")
    assert row.verdict == IN_LIMIT


def test_an_empty_table_does_not_measure_gate_l() -> None:
    evidence = timings_evidence(evaluate({}))
    assert evidence["within_limits"] is False
    assert evidence["measured"] is False
    assert "4" in evidence["unmeasured"]
    assert "12" in evidence["unmeasured"]


def test_a_row_over_the_budget_fails_even_when_other_rows_are_missing() -> None:
    evidence = timings_evidence(
        evaluate(
            {
                "1": {
                    "value": 200.0,
                    "files": 10,
                    "each_bytes": 50 * 1024 * 1024,
                    "accepted": 10,
                }
            }
        )
    )
    assert evidence["measured"] is True
    assert evidence["within_limits"] is False
    assert evidence["over"] == ["1"]
    verdicts = {item["row"]: item["verdict"] for item in evidence["rows"]}
    assert verdicts["1"] == OVER
    assert verdicts["5"] == UNMEASURED
    assert verdicts["12"] == CLAIMED


def test_executable_rules_on_an_empty_set_are_not_the_132() -> None:
    measured = measure_local()
    compared = measured["4"]
    total = compared["parameters_total"]
    expected = compared["parameters_expected"]
    assert isinstance(total, int) and isinstance(expected, int)
    assert 0 < total < expected == 132
    results = evaluate(measured)
    row = next(item for item in results if item.row.row_id == "4")
    assert row.verdict == NOT_QUOTABLE
    assert "4" in timings_evidence(results)["over"]
    assert timings_evidence(results)["within_limits"] is False


def test_compare_without_all_parameters_is_not_quotable() -> None:
    results = evaluate({"4": {"value": 10.0, "parameters_total": 55, "parameters_expected": 132}})
    row = next(item for item in results if item.row.row_id == "4")
    assert row.verdict == NOT_QUOTABLE
    evidence = timings_evidence(results)
    assert "4" in evidence["over"]


def test_api_latency_without_a_hundred_users_is_not_the_status_row() -> None:
    results = evaluate({"10": {"value": 0.018, "vu": 1, "endpoint": "healthz"}})
    row = next(item for item in results if item.row.row_id == "10")
    assert row.verdict == NOT_QUOTABLE


def test_a_real_hundred_page_text_pdf_can_be_quoted() -> None:
    results = evaluate(
        {"2": {"value": 1.0, "pages": 100, "text_layer": True, "synthetic": False}}
    )
    row = next(item for item in results if item.row.row_id == "2")
    assert row.verdict == IN_LIMIT


def test_synthetic_hundred_pages_are_timed_and_not_quoted() -> None:
    measured = measure_local()
    row_measurement = measured["2"]
    assert row_measurement["pages"] == 100
    assert row_measurement["synthetic"] is True
    assert isinstance(row_measurement["value"], float)
    results = evaluate(measured)
    row = next(item for item in results if item.row.row_id == "2")
    assert row.verdict == NOT_QUOTABLE
    assert "2" in timings_evidence(results)["over"]


def test_incremental_row_is_quotable_only_for_an_incremental_path() -> None:
    results = evaluate({"9": {"value": 1.0, "incremental": True}})
    row = next(item for item in results if item.row.row_id == "9")
    assert row.verdict == IN_LIMIT


def test_local_protocol_and_parameter_rows_are_numbers() -> None:
    measured = measure_local()
    assert measured["5"]["value"] < 30
    assert measured["7"]["value"] < 0.5
    evidence = timings_evidence(evaluate(measured))
    verdicts = {item["row"]: item["verdict"] for item in evidence["rows"]}
    assert verdicts["5"] == IN_LIMIT
    assert verdicts["7"] == IN_LIMIT
    assert verdicts["9"] == NOT_QUOTABLE
    assert isinstance(measured["9"]["value"], float)
    assert evidence["within_limits"] is False
    assert "9" in evidence["over"]
