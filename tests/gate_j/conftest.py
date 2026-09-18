"""Fixtures для Gate J frozen val recall.

Правила:
  - Без `KONTUR_FROZEN_VAL_PATH` нет корпуса — скип. CI остаётся зелёным.
  - Цифры не публикуются, пока `interval.low < 0.80`.
  - Корпус — JSONL: {"rule_code": str, "gold": str, "predicted": str|null}.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest


@pytest.fixture()
def frozen_val_path() -> pathlib.Path:
    """Путь к frozen val corpus. Скип, если переменная не выставлена."""
    env = os.environ.get('KONTUR_FROZEN_VAL_PATH')
    if not env:
        pytest.skip(
            'KONTUR_FROZEN_VAL_PATH не задан; frozen val corpus отсутствует (GAP-IOS4-VAL)'
        )
    p = pathlib.Path(env)
    if not p.is_file():
        pytest.skip(f'KONTUR_FROZEN_VAL_PATH={env} не является файлом')
    return p


@pytest.fixture()
def frozen_val_pairs(
    frozen_val_path: pathlib.Path,
) -> dict[str, list[tuple[str, str | None]]]:
    """Пары (gold, predicted) по rule_code из JSONL-корпуса.

    Формат JSONL-строки:
        {"rule_code": "IOS4-078", "gold": "150.00", "predicted": "150.00"}
        {"rule_code": "IOS4-079", "gold": "RU-2023-00001", "predicted": null}
    """
    result: dict[str, list[tuple[str, str | None]]] = {}
    with frozen_val_path.open(encoding='utf-8') as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'{frozen_val_path}:{lineno}: {exc}') from exc
            rule_code: str = row['rule_code']
            gold: str = str(row['gold'])
            predicted: str | None = row.get('predicted')  # None = пропущено
            result.setdefault(rule_code, []).append((gold, predicted))
    if not result:
        pytest.skip(f'{frozen_val_path} пуст; корпус не загружен')
    return result
