"""Gate N: frozen val метрики ≥ порогов ТЗ §13 (Red Team Gate N).

Тесты запускаются отдельно (pytest -m frozen_val) и требуют:
  KONTUR_FROZEN_VAL_PATH — путь к frozen_val.jsonl (одна JSON-запись на строку).

Формат входного файла
---------------------
Каждая строка — JSON-объект с полями:
  label     : "CANDIDATE" | <любое другое>  (истинный класс)
  predicted : "CANDIDATE" | <любое другое>  (предсказание системы)

Без файла тест автоматически пропускается — обычный CI не ломается.
С файлом — обязательные пороги:
  Recall    >= 0.80
  Precision >= 0.90
  F1        >= 0.85
  FPR       <= 0.10

Закрывает: GAP-IOS4-VAL (KNOWN_GAPS.md) — recall на frozen val не заявлялся.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

# ── конфигурация ──────────────────────────────────────────────────────────────

FROZEN_VAL_PATH: str = os.getenv("KONTUR_FROZEN_VAL_PATH", "")

RECALL_MIN: float = 0.80
PRECISION_MIN: float = 0.90
F1_MIN: float = 0.85
FPR_MAX: float = 0.10

POSITIVE_CLASS: str = "CANDIDATE"

pytestmark = pytest.mark.frozen_val


# ── фикстуры ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def frozen_val_rows() -> list[dict[str, Any]]:
    if not FROZEN_VAL_PATH:
        pytest.skip("KONTUR_FROZEN_VAL_PATH не задан — frozen val тесты пропущены")
    path = Path(FROZEN_VAL_PATH)
    if not path.exists():
        pytest.skip(f"frozen val файл не найден: {path}")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        pytest.skip("frozen val файл пуст")
    return rows


# ── вспомогательная функция ───────────────────────────────────────────────────


def _metrics(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    """Посчитать бинарные метрики (positive = CANDIDATE)."""
    tp = fp = fn = tn = 0
    for row in rows:
        label = str(row.get("label", ""))
        pred = str(row.get("predicted", ""))
        is_pos_label = label == POSITIVE_CLASS
        is_pos_pred = pred == POSITIVE_CLASS
        if is_pos_label and is_pos_pred:
            tp += 1
        elif not is_pos_label and is_pos_pred:
            fp += 1
        elif is_pos_label and not is_pos_pred:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fpr,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


# ── тесты ─────────────────────────────────────────────────────────────────────


def test_frozen_val_recall(
    frozen_val_rows: list[dict[str, Any]],
) -> None:
    """Recall >= 0.80 (ТЗ §13)."""
    m = _metrics(frozen_val_rows)
    assert m["recall"] >= RECALL_MIN, (
        f"recall={m['recall']:.3f} < {RECALL_MIN} "
        f"(tp={m['tp']}, fn={m['fn']}, n={len(frozen_val_rows)})"
    )


def test_frozen_val_precision(
    frozen_val_rows: list[dict[str, Any]],
) -> None:
    """Precision >= 0.90 (ТЗ §13)."""
    m = _metrics(frozen_val_rows)
    assert m["precision"] >= PRECISION_MIN, (
        f"precision={m['precision']:.3f} < {PRECISION_MIN} "
        f"(tp={m['tp']}, fp={m['fp']}, n={len(frozen_val_rows)})"
    )


def test_frozen_val_f1(
    frozen_val_rows: list[dict[str, Any]],
) -> None:
    """F1 >= 0.85 (ТЗ §13)."""
    m = _metrics(frozen_val_rows)
    assert m["f1"] >= F1_MIN, (
        f"f1={m['f1']:.3f} < {F1_MIN} (prec={m['precision']:.3f}, rec={m['recall']:.3f})"
    )


def test_frozen_val_fpr(
    frozen_val_rows: list[dict[str, Any]],
) -> None:
    """FPR <= 0.10 (ТЗ §13)."""
    m = _metrics(frozen_val_rows)
    assert m["fpr"] <= FPR_MAX, (
        f"fpr={m['fpr']:.3f} > {FPR_MAX} (fp={m['fp']}, tn={m['tn']})"
    )


def test_frozen_val_has_positive_examples(
    frozen_val_rows: list[dict[str, Any]],
) -> None:
    """Замороженная выборка содержит хотя бы один CANDIDATE (метрики не вырождены)."""
    positives = [r for r in frozen_val_rows if str(r.get("label", "")) == POSITIVE_CLASS]
    assert positives, (
        "frozen_val.jsonl не содержит ни одного CANDIDATE — метрики вырождены"
    )
