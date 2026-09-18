"""Loader for free-search finding definitions.

`data/matrix/free_search.json` описывает находки за пределами 132-параметровой матрицы.
Gold-нарушение FREE-HEATING-001 (тёплые полы) = VIO-0001 — матрица не покрывает.
Для Gate J recall=1.00 на всех золотых этот модуль обязателен.

Refs: GAP-FREE-SEARCH, Gate J (25.09).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_FREE_SEARCH_PATH = (
    Path(__file__).resolve().parents[6] / "data" / "matrix" / "free_search.json"
)


@dataclass
class FreeSearchRule:
    """A single free-search rule loaded from free_search.json."""

    id: str  # e.g. "FREE-HEATING-001"
    name: str
    keywords: list[str]  # text patterns to search (case-insensitive)
    stages: list[str]  # which stages to search in ("PD", "RD", "ID")
    normative_ref: str | None = None
    note: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def load_free_search_rules(
    path: Path | None = None,
) -> list[FreeSearchRule]:
    """Load free-search rules from JSON.

    Returns an empty list (not raises) if the file is missing or invalid,
    so the main pipeline does not break on missing free_search.json.

    Args:
        path: Override path for tests. Defaults to data/matrix/free_search.json.

    Returns:
        List of FreeSearchRule. Empty list on any load error.
    """
    target = path or _DEFAULT_FREE_SEARCH_PATH
    if not target.exists():
        logger.warning(
            "free_search.json not found at %s -- free-search disabled.", target
        )
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        rules = data if isinstance(data, list) else data.get("rules", [])
        return [
            FreeSearchRule(
                id=r["id"],
                name=r.get("name", r["id"]),
                keywords=r.get("keywords", []),
                stages=r.get("stages", ["PD", "RD", "ID"]),
                normative_ref=r.get("normative_ref"),
                note=r.get("note"),
                extra={k: v for k, v in r.items() if k not in (
                    "id", "name", "keywords", "stages", "normative_ref", "note"
                )},
            )
            for r in rules
        ]
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to load free_search.json from %s: %s -- free-search disabled.",
            target,
            exc,
        )
        return []
