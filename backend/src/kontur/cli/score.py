"""Счёт публичного gold. Не frozen val и не закрытие гейта J.

Совпадение — (object_id, parameter_code). В снимке gold нет location,
поэтому номер помещения в ключе не участвует. На проводе location — помещение
или «объект»; стадия и страница остаются в evidence.
Локализация — IoU полигонов на том же файле и той же странице.
Строка без эталонного полигона, файла или страницы в знаменатель не входит.
Матрица и свободный поиск не смешиваются. Порог ТЗ здесь не объявляется взятым.
Интервал F1 — кластерный bootstrap по object_id и только при 10+ кластерах.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kontur.evaluation.dataset_package import is_hidden_test_object
from kontur.evaluation.inventory import is_quarantined
from kontur.evaluation.metrics import IOU_THRESHOLD, Polygon, f1, iou, meets_threshold, wilson
from kontur.evaluation.train_public import load_run_inventory

_MIN_CLUSTERS = 10

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


def _as_polygon(raw: object) -> Polygon | None:
    """Полигон в [0;1] из JSON. Короткий или вне квадрата контур не эталон."""

    if not isinstance(raw, list) or len(raw) < 3:
        return None
    points: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            return None
        x, y = item[0], item[1]
        if isinstance(x, bool) or isinstance(y, bool):
            return None
        if not isinstance(x, int | float) or not isinstance(y, int | float):
            return None
        fx, fy = float(x), float(y)
        if not math.isfinite(fx) or not math.isfinite(fy):
            return None
        if not (0.0 <= fx <= 1.0) or not (0.0 <= fy <= 1.0):
            return None
        points.append((fx, fy))
    return tuple(points)


def _gold_page(row: Mapping[str, object]) -> tuple[str, int] | None:
    """Файл и страница эталона. Без них полигон к листу не привязан."""

    file_id = row.get("file_id")
    page = row.get("pdf_page_number")
    if not isinstance(file_id, str) or not file_id.strip():
        return None
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        return None
    return file_id.strip(), page


def _iou_localized(
    submissions: Sequence[Mapping[str, object]],
    key: tuple[str, ...],
    gold: Polygon,
    *,
    gold_file_id: str,
    gold_page: int,
) -> bool:
    """Попадание только на том же файле и той же странице, IoU не ниже порога."""

    object_id, code = key[0], key[1]
    location = key[2] if len(key) >= 3 else None
    for document in submissions:
        if str(document.get("object_id") or "") != object_id:
            continue
        checks = document.get("checks")
        if not isinstance(checks, list):
            continue
        for check in checks:
            if not isinstance(check, dict) or str(check.get("parameter_code") or "") != code:
                continue
            if location is not None and str(check.get("location") or "").strip() != location:
                continue
            evidence = check.get("evidence")
            if not isinstance(evidence, list):
                continue
            for item in evidence:
                if not isinstance(item, dict):
                    continue
                if str(item.get("file_id") or "") != gold_file_id:
                    continue
                if item.get("pdf_page_number") != gold_page:
                    continue
                predicted = _as_polygon(item.get("polygon_norm"))
                if predicted is not None and iou(gold, predicted) >= IOU_THRESHOLD:
                    return True
    return False


@dataclass(frozen=True, slots=True)
class _ScoreRow:
    object_id: str
    gold_positive: bool
    predicted_positive: bool


def _confusion(sample: Sequence[_ScoreRow]) -> tuple[int, int, int]:
    """TP, FP, FN по строкам разметки. Точка и bootstrap считают одно и то же."""

    true_positive = sum(row.gold_positive and row.predicted_positive for row in sample)
    false_positive = sum((not row.gold_positive) and row.predicted_positive for row in sample)
    false_negative = sum(row.gold_positive and not row.predicted_positive for row in sample)
    return true_positive, false_positive, false_negative


def _f1_of(sample: Sequence[_ScoreRow]) -> float:
    true_positive, false_positive, false_negative = _confusion(sample)
    predicted = true_positive + false_positive
    actual = true_positive + false_negative
    precision = true_positive / predicted if predicted else 0.0
    recall = true_positive / actual if actual else 0.0
    return f1(precision, recall)


def cluster_f1_interval(
    rows: Sequence[_ScoreRow],
    *,
    min_clusters: int = _MIN_CLUSTERS,
    draws: int = 5000,
    seed: int = 0,
) -> tuple[float, float] | None:
    """2.5 и 97.5 перцентили F1 при ресэмпле кластеров object_id.

    Меньше min_clusters кластеров — интервал не вывод. Не собирается из
    нижних границ precision и recall.
    """

    by_object: dict[str, list[_ScoreRow]] = defaultdict(list)
    for row in rows:
        by_object[row.object_id].append(row)
    ids = list(by_object)
    if len(ids) < min_clusters:
        return None
    rng = random.Random(seed)  # noqa: S311
    stats: list[float] = []
    for _ in range(draws):
        sample: list[_ScoreRow] = []
        for _cluster in range(len(ids)):
            sample.extend(by_object[rng.choice(ids)])
        stats.append(_f1_of(sample))
    stats.sort()
    last = len(stats) - 1
    return (stats[int(0.025 * last)], stats[int(0.975 * last)])


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
    localization_unscored = 0
    unscored = 0
    scorable_pos: list[Mapping[str, object]] = []
    scorable_neg: list[Mapping[str, object]] = []
    score_rows: list[_ScoreRow] = []

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
        gold_polygon = _as_polygon(row.get("polygon_norm"))
        gold_page = _gold_page(row)
        if gold_polygon is None or gold_page is None:
            localization_unscored += 1
        elif label == _POSITIVE and _iou_localized(
            submissions,
            key,
            gold_polygon,
            gold_file_id=gold_page[0],
            gold_page=gold_page[1],
        ):
            localized_hits += 1
        if label in _ABSTAIN or label is None:
            abstain += 1
        elif label == _POSITIVE:
            hits += 1
        score_rows.append(
            _ScoreRow(
                object_id=str(row["object_id"]),
                gold_positive=True,
                predicted_positive=label == _POSITIVE,
            )
        )
    for row in negatives:
        key = row_key(row)
        if key is None:
            continue
        scorable_neg.append(row)
        predicted_positive = predictions.get(key) == _POSITIVE
        score_rows.append(
            _ScoreRow(
                object_id=str(row["object_id"]),
                gold_positive=False,
                predicted_positive=predicted_positive,
            )
        )
    true_positive, row_false_positive, false_negative = _confusion(score_rows)
    recall = wilson(true_positive, true_positive + false_negative)
    precision = wilson(true_positive, true_positive + row_false_positive)
    fpr = wilson(row_false_positive, len(scorable_neg))
    point_f1 = _f1_of(score_rows)
    localization_n = len(scorable_pos) - localization_unscored
    localization = wilson(localized_hits, localization_n)
    f1_interval = cluster_f1_interval(score_rows)
    report: dict[str, object] = {
        "n_positive": len(scorable_pos),
        "hits": hits,
        "abstentions": abstain,
        "n_negative": len(scorable_neg) if by_location else len(negatives),
        "false_positives": row_false_positive,
        "localized_hits": localized_hits,
        "localization_unscored": localization_unscored,
        "localization": {
            "point": localization.point,
            "low": localization.low,
            "high": localization.high,
            "n": localization.n,
            "defined": localization.n > 0,
        },
        "f1_interval": (
            None if f1_interval is None else {"low": f1_interval[0], "high": f1_interval[1]}
        ),
        "f1_interval_note": (
            "кластеров меньше 10, bootstrap не является выводом"
            if f1_interval is None
            else "кластерный bootstrap по object_id, не нижние границы precision и recall"
        ),
        "recall": {"point": recall.point, "low": recall.low, "high": recall.high, "n": recall.n},
        "precision": {
            "point": precision.point,
            "low": precision.low,
            "high": precision.high,
            "n": precision.n,
        },
        "f1_point": point_f1,
        "fpr": {
            "point": fpr.point,
            "low": fpr.low,
            "high": fpr.high,
            "n": fpr.n,
            "defined": fpr.n > 0,
        },
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
    if fpr.get("defined") is False or fpr.get("n") == 0:
        fpr_text = "FPR не определён (n=0)"
    else:
        fpr_text = f"FPR n={fpr['n']} {fpr['point']:.3f} [{fpr['low']:.3f}; {fpr['high']:.3f}]"
    localization_block = block.get("localization")
    if not isinstance(localization_block, dict) or localization_block.get("defined") is False:
        localization_text = "локализация не определена"
    else:
        localization_text = (
            f"локализация {block['localized_hits']}/{localization_block['n']} "
            f"[{localization_block['low']:.3f}; {localization_block['high']:.3f}]"
        )
    interval = block.get("f1_interval")
    if interval is None:
        f1_text = f"F1={point_f1:.3f} интервал не вывод (кластеров < 10)"
    else:
        if not isinstance(interval, dict):
            raise TypeError(title)
        f1_text = f"F1={point_f1:.3f} bootstrap [{interval['low']:.3f}; {interval['high']:.3f}]"
    return (
        f"{title}: n={recall['n']} hits={block['hits']} "
        f"R={recall['point']:.3f} [{recall['low']:.3f}; {recall['high']:.3f}] "
        f"P n={precision['n']} {precision['point']:.3f} "
        f"[{precision['low']:.3f}; {precision['high']:.3f}] "
        f"{f1_text} "
        f"{fpr_text} "
        f"abstain={block['abstentions']} {localization_text} "
        f"localization_unscored={block['localization_unscored']} "
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
