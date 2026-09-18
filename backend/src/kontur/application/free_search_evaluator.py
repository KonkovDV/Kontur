"""Free-search evaluator — finds patterns outside the 132-rule matrix.

Searches for free-text patterns from `free_search.json` in extracted page text.
Returns `ProtocolFinding(is_free_search=True)` for each matched rule.

Fail-open: a crash in free-search MUST NOT affect the main matrix result.
All exceptions are caught and logged; caller receives an empty list.

Refs: GAP-FREE-SEARCH, FREE-HEATING-001, Gate J (25.09).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)


class _PageText:
    """Minimal page-text carrier accepted by the evaluator."""

    stage: str  # "PD", "RD", "ID"
    text: str  # normalized page text

    def __init__(self, stage: str, text: str) -> None:
        self.stage = stage
        self.text = text


def _has_keyword_match(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword matches in the text (case-insensitive, word boundary)."""
    text_lower = text.lower()
    for kw in keywords:
        if re.search(re.escape(kw.lower()), text_lower):
            return True
    return False


def evaluate_free_search(
    pages: Sequence[Any],  # Sequence of objects with .stage and .text attributes
    rules: list[Any],  # List of FreeSearchRule from free_search_loader
) -> list[dict[str, Any]]:
    """Evaluate free-search rules against extracted page text.

    Returns a list of finding dicts compatible with ProtocolFinding constructor:
        {
          "parameter_code": "FREE-HEATING-001",
          "parameter_name": ...,
          "status": "FREE_SEARCH",
          "is_free_search": True,
          "note": ...,
        }

    Fail-open: any exception returns an empty list.

    Args:
        pages: Page text objects with .stage (str) and .text (str) attributes.
        rules: FreeSearchRule list from load_free_search_rules().

    Returns:
        List of finding dicts. Empty on error.
    """
    if not rules:
        return []
    try:
        results: list[dict[str, Any]] = []
        for rule in rules:
            applicable_texts = [
                p.text for p in pages
                if p.stage in rule.stages and hasattr(p, "text")
            ]
            combined = " ".join(applicable_texts)
            if _has_keyword_match(combined, rule.keywords):
                results.append(
                    {
                        "parameter_code": rule.id,
                        "parameter_name": rule.name,
                        "status": "FREE_SEARCH",
                        "is_free_search": True,
                        "note": rule.note or f"Free-search match: {rule.id}",
                        "normative_ref": rule.normative_ref,
                    }
                )
        return results
    except Exception as exc:  # noqa: BLE001
        logger.error("Free-search evaluator failed (fail-open): %s", exc)
        return []
