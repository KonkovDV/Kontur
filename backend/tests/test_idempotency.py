"""Одинаковый вход даёт одинаковый ключ сравнения."""

from __future__ import annotations

import pytest

from kontur.domain.idempotency import comparison_key


def test_same_files_same_key() -> None:
    first = comparison_key("OBJ-1", "PZ-001", ("pd", "rd"))
    second = comparison_key("OBJ-1", "PZ-001", ("pd", "rd"))
    assert first == second
    assert len(first) == 64


def test_different_file_changes_key() -> None:
    left = comparison_key("OBJ-1", "PZ-001", ("pd", "rd"))
    right = comparison_key("OBJ-1", "PZ-001", ("pd", "rd-v2"))
    assert left != right


def test_empty_component_is_rejected() -> None:
    with pytest.raises(ValueError, match="пустых"):
        comparison_key("OBJ-1", "PZ-001", ("pd", " "))
