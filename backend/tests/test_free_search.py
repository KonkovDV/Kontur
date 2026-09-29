"""Free-search — реестр MATRIX_GAP, не 133-е правило и не FindingStatus."""

from __future__ import annotations

from pathlib import Path

from kontur.infrastructure.matrix.free_search import load_free_search

REPO = Path(__file__).resolve().parents[2]


def test_free_search_entries_are_matrix_gaps() -> None:
    entries = load_free_search(REPO / "data" / "matrix" / "free_search.json")
    assert entries
    for entry in entries:
        assert entry.mapping_status == "MATRIX_GAP"
        assert entry.matrix_scope == "FREE_SEARCH"
        assert entry.gold_ids
        assert not entry.parameter_code.startswith("PZ-")


def test_free_search_does_not_invent_finding_status() -> None:
    from kontur.domain.statuses import FindingStatus

    names = {member.name for member in FindingStatus}
    assert "FREE_SEARCH" not in names
