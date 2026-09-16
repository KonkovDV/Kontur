"""Инвентаризация датасета и аудит утечки (см. docs/DATA_QUARANTINE.md).

Запускается до любой разработки модели. Каталог карантина не открывается:
скрипт считает только хеши и имена архивов, не содержимое разметки.
"""

from __future__ import annotations

from pathlib import Path

QUARANTINE_MARKERS = ("TEST_213", "annotated_documents")


def is_quarantined(path: Path) -> bool:
    """Путь относится к карантину скрытого теста."""

    text = str(path)
    return any(marker in text for marker in QUARANTINE_MARKERS)


def hash_archives(incoming: Path) -> dict[str, str]:
    """SHA-256 каждого архива до распаковки."""

    raise NotImplementedError("Gate A")


def build_manifest(work_dir: Path) -> dict[str, object]:
    """Манифест: объект, стадия, дисциплина, шифр, редакция, утверждение, качество."""

    raise NotImplementedError("Gate A")


def audit_split_leakage(manifest: dict[str, object]) -> list[str]:
    """Пересечение train/validation по object_id. Должно быть пустым."""

    raise NotImplementedError("Gate A")
