"""Счёт публичного gold. Не frozen val и не закрытие гейта J.

Совпадение — (object_id, parameter_code). В снимке gold нет location,
поэтому локализация считается отдельно: есть ли у попадания file_id и страница.
Матрица и свободный поиск не смешиваются. Порог ТЗ здесь не объявляется взятым.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from kontur.evaluation.dataset_package import is_hidden_test_object
from kontur.evaluation.inventory import is_quarantined
from kontur.evaluation.metrics import f1, meets_threshold, wilson
from kontur.evaluation.train_public import load_run_inventory

_POSITIVE = "VIOLATION_PRESENT"
_ABSTAIN = frozenset({"COMPARISON_IMPOSSIBLE", "MISSING_DOCUMENT"})


def _rows(inventory: Mapping[str, object]) -> list[dict[str, object]]:
    checks = inventory["public_gold_checks"]
    if not isinstance(checks, dict):
        raise TypeError("public_gold_checks")
    raw = checks["rows"]
    if not isinstance(raw, list):
        raise TypeError("public_gold_checks.rows")
    rows: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError("gold row")
        object_id = str(item.get("object_id") or "")
        if is_hidden_test_object(object_id):
            raise ValueError(f"{object_id}: скрытый тест в счёт не берётся")
        rows.append(item)
    return rows


def _load_submissions(folder: Path) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    if not folder.is_dir():
        raise ValueError(f"{folder}: не каталог")
    for path in sorted(folder.glob("submission_*.json")):
        if is_quarantined(path):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path.name}: ожидался объект")
        object_id = str(payload.get("object_id") or "")
        if is_hidden_test_object(object_id):
            raise ValueError(f"{object_id}: скрытый тест в счёт не берётся")
        found.append(payload)
    return found


def _predictions(submissions: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], str]:
    """Одна метка на (объект, код). VIOLATION_PRESENT перекрывает более слабую."""

    labels: dict[tuple[str, str], str] = {}
    for document in submissions:
        object_id = str(document.get("object_id") or "")
        checks = document.get("checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict):
                continue
            code = str(check.get("parameter_code") or "")
            label = str(check.get("violation_label") or "")
            if not object_id or not code or not label:
                continue
            key = (object_id, code)
            if labels.get(key) == _POSITIVE:
                continue
            labels[key] = label
    return labels


def _localized(submissions: Sequence[Mapping[str, object]], key: tuple[str, str]) -> bool:
    object_id, code = key
    for document in submissions:
        if str(document.get("object_id") or "") != object_id:
            continue
        checks = document.get("checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict) or str(check.get("parameter_code") or "") != code:
                continue
            evidence = check.get("evidence")
            if not isinstance(evidence, list):
                continue
            for item in evidence:
                if not isinstance(item, dict):
                    continue
                page = item.get("pdf_page_number")
                if str(item.get("file_id") or "").strip() and isinstance(page, int) and page >= 1:
                    return True
    return False


def _scope_rows(rows: Sequence[Mapping[str, object]], scope: str) -> list[Mapping[str, object]]:
    return [row for row in rows if row.get("matrix_scope") == scope]


def score_scope(
    rows: Sequence[Mapping[str, object]],
    predictions: Mapping[tuple[str, str], str],
    submissions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    positives = [row for row in rows if row.get("violation_label") == _POSITIVE]
    negatives = [row for row in rows if row.get("violation_label") == "NO_VIOLATION"]
    hits = 0
    abstain = 0
    localized_hits = 0
    for row in positives:
        key = (str(row["object_id"]), str(row["parameter_code"]))
        label = predictions.get(key)
        if label in _ABSTAIN or label is None:
            abstain += 1
            continue
        if label == _POSITIVE:
            hits += 1
            if _localized(submissions, key):
                localized_hits += 1
    false_positives = 0
    for row in negatives:
        key = (str(row["object_id"]), str(row["parameter_code"]))
        if predictions.get(key) == _POSITIVE:
            false_positives += 1
    predicted_keys = {
        key
        for key, label in predictions.items()
        if label == _POSITIVE and any(
            str(row["object_id"]) == key[0] and str(row["parameter_code"]) == key[1] for row in rows
        )
    }
    true_keys = {
        (str(row["object_id"]), str(row["parameter_code"]))
        for row in positives
    }
    tp_keys = predicted_keys & true_keys
    fp_keys = predicted_keys - true_keys
    recall = wilson(hits, len(positives))
    precision = wilson(len(tp_keys), len(tp_keys) + len(fp_keys))
    fpr = wilson(false_positives, len(negatives))
    point_f1 = f1(precision.point, recall.point)
    return {
        "n_positive": len(positives),
        "hits": hits,
        "abstentions": abstain,
        "n_negative": len(negatives),
        "false_positives": false_positives,
        "localized_hits": localized_hits,
        "recall": {"point": recall.point, "low": recall.low, "high": recall.high, "n": recall.n},
        "precision": {
            "point": precision.point,
            "low": precision.low,
            "high": precision.high,
            "n": precision.n,
        },
        "f1_point": point_f1,
        "fpr": {"point": fpr.point, "low": fpr.low, "high": fpr.high, "n": fpr.n},
        "tz_recall_met": meets_threshold("recall", recall),
        "tz_precision_met": meets_threshold("precision", precision) if precision.n else False,
        "tz_fpr_met": meets_threshold("false_positive_rate", fpr) if fpr.n else False,
    }


def score_directory(folder: Path) -> dict[str, object]:
    inventory = load_run_inventory()
    rows = _rows(inventory)
    submissions = _load_submissions(folder)
    predictions = _predictions(submissions)
    report = {
        "closes_gate_j": False,
        "corpus": "public_gold_checks",
        "not_frozen_val": True,
        "match": "object_id+parameter_code",
        "location_in_gold": False,
        "matrix": score_scope(_scope_rows(rows, "MATRIX"), predictions, submissions),
        "free_search": score_scope(_scope_rows(rows, "FREE_SEARCH"), predictions, submissions),
    }
    return report


def _line(title: str, block: Mapping[str, object]) -> str:
    recall = block["recall"]
    precision = block["precision"]
    fpr = block["fpr"]
    if not isinstance(recall, dict) or not isinstance(precision, dict) or not isinstance(fpr, dict):
        raise TypeError(title)
    point_f1 = block["f1_point"]
    if not isinstance(point_f1, float):
        raise TypeError(title)
    return (
        f"{title}: n={recall['n']} hits={block['hits']} "
        f"R={recall['point']:.3f} [{recall['low']:.3f}; {recall['high']:.3f}] "
        f"P n={precision['n']} {precision['point']:.3f} "
        f"[{precision['low']:.3f}; {precision['high']:.3f}] "
        f"F1={point_f1:.3f} "
        f"FPR n={fpr['n']} {fpr['point']:.3f} [{fpr['low']:.3f}; {fpr['high']:.3f}] "
        f"abstain={block['abstentions']} localized_hits={block['localized_hits']} "
        f"порог_ТЗ={block['tz_recall_met']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Счёт публичного gold по submission_*.json")
    parser.add_argument("--submissions", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = score_directory(args.submissions)
    except (ValueError, OSError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    matrix = report["matrix"]
    free = report["free_search"]
    if not isinstance(matrix, dict) or not isinstance(free, dict):
        raise TypeError("score")
    print("публичная разметка, не frozen val. Порог ТЗ по нижней границе Wilson не заявлен взятым.")
    print(_line("MATRIX", matrix))
    print(_line("FREE_SEARCH", free))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
