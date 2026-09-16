"""Инвентаризация датасета и аудит утечки (см. docs/DATA_QUARANTINE.md).

Запускается до любой разработки модели. Каталог карантина не открывается:
скрипт считает только хеши и имена архивов, не содержимое разметки.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

#: Маркеры карантина в нормализованном виде: нижний регистр, одиночные `_`.
#: Имена организатора нестабильны — в поставке встречаются и
#: `РАЗМЕЧЕННЫЙ_TEST__213.zip` (два подчёркивания), и внутренний каталог
#: `РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213`. Точное сравнение имён такие
#: варианты пропускает, поэтому сравнение идёт по нормализованной строке.
QUARANTINE_MARKERS = (
    "test_213",
    "test_hidden",
    "hidden_организатор",
    "annotated_documents",
)

_REPEATED_UNDERSCORES = re.compile(r"_+")


def normalize(path: Path | str) -> str:
    """Схлопывает повторяющиеся `_` и снимает регистр (в т. ч. кириллица)."""

    return _REPEATED_UNDERSCORES.sub("_", str(path)).casefold()


def is_quarantined(path: Path | str) -> bool:
    """Путь относится к карантину скрытого теста."""

    text = normalize(path)
    return any(marker in text for marker in QUARANTINE_MARKERS)


def quarantine_hits(paths: Iterable[Path | str]) -> list[str]:
    """Пути, помеченные как карантин. Пустой список — можно продолжать."""

    return [str(path) for path in paths if is_quarantined(path)]


def hash_archives(incoming: Path) -> dict[str, str]:
    """SHA-256 каждого архива до распаковки."""

    raise NotImplementedError("Gate A")


def build_manifest(work_dir: Path) -> dict[str, object]:
    """Манифест: объект, стадия, дисциплина, шифр, редакция, утверждение, качество."""

    raise NotImplementedError("Gate A")


def audit_split_leakage(manifest: dict[str, object]) -> list[str]:
    """Пересечение train/validation по object_id. Должно быть пустым."""

    raise NotImplementedError("Gate A")
