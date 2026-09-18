"""Замер на frozen val — opt-in. Без пути корпус не трогаем и цифры не публикуем."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENV = "KONTUR_FROZEN_VAL_PATH"


def test_frozen_val_is_skipped_without_corpus_path() -> None:
    path = os.environ.get(_ENV)
    if not path:
        pytest.skip(f"{_ENV} не задан; recall/P/F1 на frozen val не измеряются")
    corpus = Path(path)
    if not corpus.exists():
        pytest.skip(f"{_ENV} указывает на отсутствующий путь: {corpus}")
    pytest.skip("замер метрик на frozen val не в этом прогоне: порог приёмки не публикуется")
