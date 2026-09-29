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
#:
#: `annotated_documents` сюда не входит: этот каталог есть и у открытого train,
#: и у скрытого теста. Карантин скрытой разметки ловится именем теста или
#: компонентом пути `quarantine`.
QUARANTINE_MARKERS = (
    "test_213",
    "test_hidden",
    "hidden_организатор",
)

_QUARANTINE_DIR = "quarantine"
_REPEATED_UNDERSCORES = re.compile(r"_+")
_PATH_SEPARATORS = re.compile(r"[\\/]+")


class QuarantineViolation(RuntimeError):
    """Попытка использовать карантинный артефакт в эксперименте."""


def normalize(path: Path | str) -> str:
    """Схлопывает повторяющиеся `_` и снимает регистр (в т. ч. кириллица)."""

    return _REPEATED_UNDERSCORES.sub("_", str(path)).casefold()


def _path_parts(path: Path | str) -> tuple[str, ...]:
    """Компоненты пути и для POSIX, и для Windows-строки на Linux CI."""

    return tuple(part for part in _PATH_SEPARATORS.split(str(path)) if part)


def is_quarantined(path: Path | str) -> bool:
    """Путь относится к карантину скрытого теста.

    Имя `annotated_documents` само по себе не карантин: открытый train
    распаковывается с тем же каталогом. Карантин — скрытый тест (маркеры) или
    дерево `data/quarantine/`.
    """

    text = normalize(path)
    if any(marker in text for marker in QUARANTINE_MARKERS):
        return True
    return any(normalize(part) == _QUARANTINE_DIR for part in _path_parts(path))


def quarantine_hits(paths: Iterable[Path | str]) -> list[str]:
    """Пути, помеченные как карантин. Пустой список — можно продолжать."""

    return [str(path) for path in paths if is_quarantined(path)]


def require_path_open(path: Path | str) -> Path:
    """Барьер по пути: карантинное имя или дерево `quarantine/` не читаются."""

    target = Path(path)
    if is_quarantined(target):
        raise QuarantineViolation(
            f"{target}: карантин скрытого теста, чтение запрещено "
            "(docs/DATA_QUARANTINE.md)"
        )
    return target


def hash_archives(incoming: Path) -> dict[str, str]:
    """SHA-256 открытых архивов до распаковки.

    Карантинные имена **пропускаются**, а не валят всю партию: иначе поставка
    с `РАЗМЕЧЕННЫЙ_TEST__213.zip` в `data/incoming/` блокирует Gate A.
    Сами карантинные файлы этим контуром не читаются и не хешируются.
    """

    files: list[Path] = []
    if incoming.exists():
        files = sorted(
            path
            for path in incoming.rglob("*")
            if path.is_file() and not is_quarantined(path)
        )
    if not files:
        return {}
    raise NotImplementedError("Gate A: SHA-256 pending")


def build_manifest(work_dir: Path) -> dict[str, object]:
    """Манифест: объект, стадия, дисциплина, шифр, редакция, утверждение, качество."""

    raise NotImplementedError("Gate A")


def audit_split_leakage(manifest: dict[str, object]) -> list[str]:
    """Пересечение train/validation по object_id. Должно быть пустым."""

    raise NotImplementedError("Gate A")
