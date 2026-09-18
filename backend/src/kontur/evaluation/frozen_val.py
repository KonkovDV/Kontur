"""Замер recall на frozen val. Без корпуса цифры не публикуются.

Синтетический gold=pred и `tests/gate_j` вне pytest сюда не входят.
Порог ТЗ считается по нижней границе Wilson, не по точечной оценке.
Карантин скрытого теста (`test_213`, TEST_HIDDEN) читать нельзя.
Строка JSONL обязана нести `object_id`: разбиение — по объекту, не по файлу.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kontur.evaluation.inventory import require_path_open
from kontur.evaluation.metrics import Interval, meets_threshold, wilson

FROZEN_VAL_ENV = "KONTUR_FROZEN_VAL_PATH"


@dataclass(frozen=True, slots=True)
class FrozenValRow:
    object_id: str
    rule_code: str
    gold_positive: bool
    predicted_positive: bool


def resolve_corpus_path(env: Mapping[str, str] | None = None) -> Path | None:
    """Путь корпуса или None, если замер не запрошен. Карантин — исключение."""

    raw = (env or os.environ).get(FROZEN_VAL_ENV)
    if not raw or not raw.strip():
        return None
    return require_path_open(Path(raw))


def critical_recall(gold_positive: Sequence[bool], predicted: Sequence[bool]) -> Interval:
    """Recall по критическим позитивам. Длины обязаны совпадать."""

    if len(gold_positive) != len(predicted):
        raise ValueError("gold и pred разной длины")
    n = sum(1 for item in gold_positive if item)
    hits = sum(
        1
        for gold, pred in zip(gold_positive, predicted, strict=True)
        if gold and pred
    )
    return wilson(hits, n)


def recall_meets_tz(interval: Interval) -> bool:
    """True только если нижняя граница Wilson ≥ порога ТЗ."""

    return meets_threshold("recall", interval)


def _as_bool(raw: object, *, field: str) -> bool:
    if isinstance(raw, bool):
        return raw
    raise TypeError(f"{field} должен быть bool, получено {raw!r}")


def load_frozen_val_jsonl(path: Path) -> tuple[FrozenValRow, ...]:
    """Читает JSONL. Без object_id — ошибка, не skip. Карантин — отказ."""

    target = require_path_open(path)
    rows: list[FrozenValRow] = []
    for index, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"{target}:{index}: ожидался объект")
        object_id = str(payload.get("object_id") or "").strip()
        rule_code = str(payload.get("rule_code") or "").strip()
        if not object_id:
            raise ValueError(f"{target}:{index}: нет object_id")
        if not rule_code:
            raise ValueError(f"{target}:{index}: нет rule_code")
        rows.append(
            FrozenValRow(
                object_id=object_id,
                rule_code=rule_code,
                gold_positive=_as_bool(payload.get("gold_positive"), field="gold_positive"),
                predicted_positive=_as_bool(
                    payload.get("predicted_positive"), field="predicted_positive"
                ),
            )
        )
    return tuple(rows)


def recall_for_rule(rows: Sequence[FrozenValRow], rule_code: str) -> Interval:
    subset = [row for row in rows if row.rule_code == rule_code]
    return critical_recall(
        [row.gold_positive for row in subset],
        [row.predicted_positive for row in subset],
    )
