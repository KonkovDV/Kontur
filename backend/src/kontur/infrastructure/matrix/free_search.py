"""Реестр free-search: это MATRIX_GAP, не 133-е правило и не статус находки."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FreeSearchEntry:
    parameter_code: str
    title: str
    gold_ids: tuple[str, ...]
    mapping_status: str
    action: str
    matrix_scope: str


def load_free_search(path: Path) -> tuple[FreeSearchEntry, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("entries")
    if not isinstance(raw, list):
        raise ValueError("free_search.json: нет entries")
    entries: list[FreeSearchEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("free_search.json: элемент не объект")
        gold = item.get("gold_ids")
        if not isinstance(gold, list):
            raise ValueError("free_search.json: нет gold_ids")
        status = str(item.get("mapping_status") or "")
        if status != "MATRIX_GAP":
            code = item.get("parameter_code")
            raise ValueError(f"free_search.json: {code} не MATRIX_GAP")
        entries.append(
            FreeSearchEntry(
                parameter_code=str(item["parameter_code"]),
                title=str(item["title"]),
                gold_ids=tuple(str(value) for value in gold),
                mapping_status=status,
                action=str(item.get("action") or ""),
                matrix_scope=str(item.get("matrix_scope") or ""),
            )
        )
    return tuple(entries)
