"""Адаптер submission_schema: внутренний статус ≠ метка хакатона."""

from __future__ import annotations

from kontur.domain.statuses import WIRE_FINDING_STATUSES, FindingStatus
from kontur.evaluation.submission import (
    ContestViolationLabel,
    contest_allows_auto_no_difference,
    contest_violation_label,
)


def test_two_wires_diverge_on_auto_no_difference() -> None:
    assert contest_allows_auto_no_difference()
    assert FindingStatus.AUTO_NO_DIFFERENCE not in WIRE_FINDING_STATUSES
    assert (
        contest_violation_label(FindingStatus.AUTO_NO_DIFFERENCE)
        is ContestViolationLabel.NO_VIOLATION
    )


def test_candidate_is_contest_detection_not_confirmed_violation() -> None:
    assert (
        contest_violation_label(FindingStatus.CANDIDATE)
        is ContestViolationLabel.VIOLATION_PRESENT
    )
    assert FindingStatus.CANDIDATE in WIRE_FINDING_STATUSES


def test_human_only_statuses_map_without_rewriting_domain() -> None:
    assert (
        contest_violation_label(FindingStatus.CONFIRMED_VIOLATION)
        is ContestViolationLabel.VIOLATION_PRESENT
    )
    assert (
        contest_violation_label(FindingStatus.NEGATIVE_VERIFIED)
        is ContestViolationLabel.NO_VIOLATION
    )


def test_data_quality_does_not_become_a_violation_on_contest_wire() -> None:
    assert (
        contest_violation_label(FindingStatus.MISSING_EVIDENCE)
        is ContestViolationLabel.MISSING_DOCUMENT
    )
    assert (
        contest_violation_label(FindingStatus.ABSTAIN)
        is ContestViolationLabel.COMPARISON_IMPOSSIBLE
    )
    assert (
        contest_violation_label(FindingStatus.SUSPICION)
        is ContestViolationLabel.COMPARISON_IMPOSSIBLE
    )


def test_every_finding_status_has_contest_mapping() -> None:
    for status in FindingStatus:
        assert isinstance(contest_violation_label(status), ContestViolationLabel)
