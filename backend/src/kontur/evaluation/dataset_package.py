"""Реестр переданного организатором пакета данных (см. docs/DATASET_PACKAGE.md).

`data/dataset/package_manifest.json` — единственный machine-readable источник о
составе поставки. Модуль не открывает архивы и не читает разметку: он отвечает
на один вопрос — что разрешено брать в эксперимент, а что лежит в карантине.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from kontur.evaluation.inventory import QuarantineViolation, is_quarantined

MANIFEST_PATH: Final[Path] = (
    Path(__file__).resolve().parents[4] / "data" / "dataset" / "package_manifest.json"
)

OPEN_ACCESS: Final[str] = "open"
QUARANTINE_ACCESS: Final[str] = "quarantine"
ACCESS_MODES: Final[frozenset[str]] = frozenset({OPEN_ACCESS, QUARANTINE_ACCESS})
HIDDEN_TEST_KIND: Final[str] = "annotated_hidden_test"

__all__ = (
    "ACCESS_MODES",
    "MANIFEST_PATH",
    "HIDDEN_TEST_KIND",
    "OPEN_ACCESS",
    "QUARANTINE_ACCESS",
    "PackageEntry",
    "QuarantineViolation",
    "load_entries",
    "load_manifest",
    "object_ids",
    "pending_hashes",
    "require_open",
    "total_size_kb",
    "usable_for_experiments",
)


@dataclass(frozen=True, slots=True)
class PackageEntry:
    """Одна единица поставки: архив, PDF ТЗ или шаблон презентации."""

    name: str
    kind: str
    access: str
    object_id: str | None
    size_kb: int
    sha256: str | None
    notes: str

    @property
    def is_quarantined(self) -> bool:
        return self.access == QUARANTINE_ACCESS

    @property
    def hash_pending(self) -> bool:
        """SHA-256 ещё не зафиксирован — долг Gate A, а не норма."""

        return self.sha256 is None


def _require(item: dict[str, object], key: str) -> object:
    if key not in item:
        raise ValueError(f"запись манифеста без поля {key!r}")
    return item[key]


def _as_str(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"поле {key!r}: ожидалась строка, получено {type(value).__name__}")
    return value


def _as_optional_str(value: object, key: str) -> str | None:
    return None if value is None else _as_str(value, key)


def _as_int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"поле {key!r}: ожидалось целое, получено {type(value).__name__}")
    return value


def _entry_from_raw(raw: object) -> PackageEntry:
    if not isinstance(raw, dict):
        raise TypeError("запись манифеста должна быть объектом JSON")
    item: dict[str, object] = raw
    access = _as_str(_require(item, "access"), "access")
    if access not in ACCESS_MODES:
        raise ValueError(f"неизвестный режим доступа {access!r}")
    kind = _as_str(_require(item, "kind"), "kind")
    if kind == HIDDEN_TEST_KIND and access != QUARANTINE_ACCESS:
        raise ValueError(
            f"{item.get('name')!r}: kind {HIDDEN_TEST_KIND!r} обязан иметь access=quarantine"
        )
    return PackageEntry(
        name=_as_str(_require(item, "name"), "name"),
        kind=kind,
        access=access,
        object_id=_as_optional_str(item.get("object_id"), "object_id"),
        size_kb=_as_int(_require(item, "size_kb"), "size_kb"),
        sha256=_as_optional_str(item.get("sha256"), "sha256"),
        notes=_as_str(item.get("notes", ""), "notes"),
    )


def load_manifest(path: Path | None = None) -> dict[str, object]:
    """Читает манифест как есть, без интерпретации."""

    target = MANIFEST_PATH if path is None else path
    with target.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise TypeError("манифест должен быть объектом JSON")
    result: dict[str, object] = payload
    return result


def load_entries(path: Path | None = None) -> tuple[PackageEntry, ...]:
    """Типизированный разбор списка `entries`."""

    raw_entries = load_manifest(path).get("entries")
    if not isinstance(raw_entries, list):
        raise TypeError("манифест: поле 'entries' должно быть списком")
    return tuple(_entry_from_raw(item) for item in raw_entries)


def _blocked(entry: PackageEntry) -> bool:
    """Карантин, если так сказал манифест **или** детектор имён (fail-closed)."""

    return entry.is_quarantined or is_quarantined(entry.name)


def usable_for_experiments(entries: Iterable[PackageEntry]) -> tuple[PackageEntry, ...]:
    """Артефакты, которые разрешено распаковывать и читать."""

    return tuple(entry for entry in entries if not _blocked(entry))


def require_open(entry: PackageEntry) -> PackageEntry:
    """Барьер перед любым чтением: карантин не идёт ни в обучение, ни в подбор порогов.

    Fail-closed: отказ, если карантин говорит манифест **или** детектор имён.
    Расхождение двух источников ловит `test_quarantine_detector_agrees_with_manifest`.
    """

    if _blocked(entry):
        raise QuarantineViolation(
            f"{entry.name}: карантин скрытого теста, чтение запрещено "
            "(docs/DATA_QUARANTINE.md)"
        )
    return entry


def pending_hashes(entries: Iterable[PackageEntry]) -> tuple[str, ...]:
    """Имена единиц поставки без зафиксированного SHA-256."""

    return tuple(entry.name for entry in entries if entry.hash_pending)


def object_ids(entries: Iterable[PackageEntry]) -> tuple[str, ...]:
    """Идентификаторы объектов в порядке манифеста, без повторов."""

    seen: list[str] = []
    for entry in entries:
        if entry.object_id is not None and entry.object_id not in seen:
            seen.append(entry.object_id)
    return tuple(seen)


def total_size_kb(entries: Iterable[PackageEntry]) -> int:
    """Суммарный объём поставки в КБ — вход для расчёта бюджета диска."""

    return sum(entry.size_kb for entry in entries)
