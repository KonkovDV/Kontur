"""Реестр free-search: это MATRIX_GAP, не 133-е правило и не статус находки."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kontur.infrastructure.matrix.registry import discover_matrix_root


@dataclass(frozen=True, slots=True)
class FreeSearchEntry:
    parameter_code: str
    title: str
    gold_ids: tuple[str, ...]
    mapping_status: str
    action: str
    matrix_scope: str
    room_compare: dict[str, object] | None = None


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
        raw_room = item.get("room_compare")
        entries.append(
            FreeSearchEntry(
                parameter_code=str(item["parameter_code"]),
                title=str(item["title"]),
                gold_ids=tuple(str(value) for value in gold),
                mapping_status=status,
                action=str(item.get("action") or ""),
                matrix_scope=str(item.get("matrix_scope") or ""),
                room_compare=raw_room if isinstance(raw_room, dict) else None,
            )
        )
    return tuple(entries)


def wire_codes(matrix_codes: Sequence[str], path: Path | None = None) -> list[str]:
    """Коды матрицы плюс free-search. В реестр 132 они не входят."""

    catalog = path or (discover_matrix_root() / "free_search.json")
    extra = (
        [entry.parameter_code for entry in load_free_search(catalog)]
        if catalog.is_file()
        else []
    )
    codes: list[str] = []
    for code in (*matrix_codes, *extra):
        if code not in codes:
            codes.append(code)
    return codes
