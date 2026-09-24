"""Счёт публичного gold. Не frozen val и не закрытие гейта J.

Совпадение — (object_id, parameter_code). В снимке gold нет location,
поэтому номер помещения в ключе не участвует. На проводе location — помещение
или «объект»; стадия и страница остаются в evidence.
Локализация считается отдельно: есть ли у попадания file_id и страница.
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


def _predictions(submissions: Sequence[Mapping[str, object]]) -> dict[tuple[str, ...], str]:
    """Одна метка на (объект, код). VIOLATION_PRESENT перекрывает более слабую."""

    labels: dict[tuple[str, ...], str] = {}
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
            key: tuple[str, ...] = (object_id, code)
            if labels.get(key) == _POSITIVE:
                continue
            labels[key] = label
    return labels


def _predictions_by_location(
    submissions: Sequence[Mapping[str, object]],
) -> dict[tuple[str, ...], str]:
    """Метка на (объект, код, location). Номер помещения из gold не выдумывается."""

    labels: dict[tuple[str, ...], str] = {}
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
            location = str(check.get("location") or "").strip()
            if not object_id or not code or not label or not location:
                continue
            key = (object_id, code, location)
            if labels.get(key) == _POSITIVE:
                continue
            labels[key] = label
    return labels


def _gold_location(row: Mapping[str, object]) -> str | None:
    raw = row.get("location")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def _localized(submissions: Sequence[Mapping[str, object]], key: tuple[str, ...]) -> bool:
    object_id, code = key[0], key[1]
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
    predictions: Mapping[tuple[str, ...], str],
    submissions: Sequence[Mapping[str, object]],
    *,
    by_location: bool = False,
) -> dict[str, object]:
    positives = [row for row in rows if row.get("violation_label") == _POSITIVE]
    negatives = [row for row in rows if row.get("violation_label") == "NO_VIOLATION"]
    hits = 0
    abstain = 0
    localized_hits = 0
    unscored = 0
    scorable_pos: list[Mapping[str, object]] = []
    scorable_neg: list[Mapping[str, object]] = []

    def row_key(row: Mapping[str, object]) -> tuple[str, ...] | None:
        code_key = (str(row["object_id"]), str(row["parameter_code"]))
        if not by_location:
            return code_key
        location = _gold_location(row)
        if location is None:
            return None
        return (*code_key, location)

    for row in positives:
        key = row_key(row)
        if key is None:
            unscored += 1
            continue
        scorable_pos.append(row)
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
        key = row_key(row)
        if key is None:
            continue
        scorable_neg.append(row)
        if predictions.get(key) == _POSITIVE:
            false_positives += 1
    predicted_keys = {
        key
        for key, label in predictions.items()
        if label == _POSITIVE and any(
            str(row["object_id"]) == key[0] and str(row["parameter_code"]) == key[1] for row in rows
        )
    }
    true_keys = {key for row in scorable_pos if (key := row_key(row)) is not None}
    if by_location:
        true_keys = {key for key in true_keys if len(key) == 3}
        predicted_keys = {key for key in predicted_keys if len(key) == 3}
    tp_keys = predicted_keys & true_keys
    fp_keys = predicted_keys - true_keys
    recall = wilson(hits, len(scorable_pos))
    precision = wilson(len(tp_keys), len(tp_keys) + len(fp_keys))
    fpr = wilson(false_positives, len(scorable_neg))
    point_f1 = f1(precision.point, recall.point)
    report: dict[str, object] = {
        "n_positive": len(scorable_pos),
        "hits": hits,
        "abstentions": abstain,
        "n_negative": len(scorable_neg) if by_location else len(negatives),
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
    if by_location:
        report["unscored_without_location"] = unscored
    return report


def score_directory(folder: Path, *, match: str = "code") -> dict[str, object]:
    if match not in {"code", "location"}:
        raise ValueError("match: code или location")
    inventory = load_run_inventory()
    rows = _rows(inventory)
    submissions = _load_submissions(folder)
    by_location = match == "location"
    predictions = (
        _predictions_by_location(submissions) if by_location else _predictions(submissions)
    )
    location_in_gold = any(_gold_location(row) is not None for row in rows)
    report = {
        "closes_gate_j": False,
        "corpus": "public_gold_checks",
        "not_frozen_val": True,
        "match": "object_id+parameter_code+location" if by_location else "object_id+parameter_code",
        "location_in_gold": location_in_gold,
        "matrix": score_scope(
            _scope_rows(rows, "MATRIX"), predictions, submissions, by_location=by_location
        ),
        "free_search": score_scope(
            _scope_rows(rows, "FREE_SEARCH"), predictions, submissions, by_location=by_location
        ),
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
    parser.add_argument("--match", choices=("code", "location"), default="code")
    args = parser.parse_args(argv)
    try:
        report = score_directory(args.submissions, match=args.match)
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
