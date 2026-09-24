"""Допуск: фикстуры без списка фамилий и без меток скрытого теста.

Список фамилий лежит вне git. На CI файла нет — проверка пропускается.
Инвентарь карантина может называть объект, чтобы его не открывали.
Метки ответов в jsonl быть не должно.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = (REPO / "backend" / "tests", REPO / "backend" / "src", REPO / "docs", REPO / "data")
_TEXT_SUFFIXES = {".py", ".md", ".json", ".jsonl", ".yml", ".yaml", ".tsx", ".ts", ".txt"}
_QUARANTINE_INVENTORY = {
    REPO / "data" / "dataset" / "agent_handoff.json",
    REPO / "data" / "dataset" / "gold_inventory.json",
    REPO / "data" / "dataset" / "objects.json",
    REPO / "data" / "dataset" / "package_manifest.json",
}
_HIDDEN_MARKERS = ("OBJ-RECHNIKOV-7-7", "TEST_213", "РАЗМЕЧЕННЫЙ_TEST")


def _forbidden_names_file() -> Path | None:
    raw = os.environ.get("KONTUR_FORBIDDEN_NAMES_FILE", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_file() else None
    outside_repo = REPO.parent / "kontur-forbidden-names.txt"
    if outside_repo.is_file():
        return outside_repo
    home = Path.home() / "kontur-forbidden-names.txt"
    return home if home.is_file() else None


def _forbidden_names() -> list[str]:
    path = _forbidden_names_file()
    if path is None:
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def test_no_real_names_in_fixtures() -> None:
    names = _forbidden_names()
    if not names:
        pytest.skip("нет внешнего списка фамилий")
    hits: list[str] = []
    for root in _SCAN_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name in names:
                if name in text:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == []


def test_no_test_labels_in_repo() -> None:
    hits: list[str] = []
    data = REPO / "data"
    for path in data.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        if path.resolve() in {item.resolve() for item in _QUARANTINE_INVENTORY}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in _HIDDEN_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(REPO)}: {marker}")
    assert hits == []
