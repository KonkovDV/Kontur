"""Инварианты машин состояний. Падение любого теста — дефект класса S0."""

from __future__ import annotations

import pytest

from kontur.domain.state_machines import (
    Actor,
    TransitionError,
    advance_finding,
    advance_process,
    unfinalize,
)
from kontur.domain.statuses import FindingStatus, ProcessState

INSPECTOR = Actor(actor_id="inspector-1", is_human=True)
MACHINE = Actor(actor_id="matrix-engine", is_human=False)
LLM = Actor(actor_id="vlm-ocr", is_human=False)


def test_machine_cannot_confirm_violation() -> None:
    with pytest.raises(TransitionError):
        advance_finding(FindingStatus.CANDIDATE, FindingStatus.CONFIRMED_VIOLATION, MACHINE)


def test_llm_cannot_confirm_violation() -> None:
    with pytest.raises(TransitionError):
        advance_finding(FindingStatus.CANDIDATE, FindingStatus.CONFIRMED_VIOLATION, LLM)


def test_machine_cannot_write_negative_verified() -> None:
    """Автомат пишет AUTO_NO_DIFFERENCE; GOLD-метку ставит человек."""

    with pytest.raises(TransitionError):
        advance_finding(FindingStatus.AUTO_NO_DIFFERENCE, FindingStatus.NEGATIVE_VERIFIED, MACHINE)


def test_inspector_confirms_candidate() -> None:
    result = advance_finding(FindingStatus.CANDIDATE, FindingStatus.CONFIRMED_VIOLATION, INSPECTOR)
    assert result is FindingStatus.CONFIRMED_VIOLATION


def test_missing_evidence_never_becomes_violation() -> None:
    with pytest.raises(TransitionError):
        advance_finding(
            FindingStatus.MISSING_EVIDENCE, FindingStatus.CONFIRMED_VIOLATION, INSPECTOR
        )


def test_not_applicable_inspector_may_confirm_applicability() -> None:
    """ТЗ п. 9.2: инспектор подтверждает применимость. Автомат не может."""

    with pytest.raises(TransitionError):
        advance_finding(FindingStatus.NOT_APPLICABLE, FindingStatus.CANDIDATE, MACHINE)
    assert (
        advance_finding(FindingStatus.NOT_APPLICABLE, FindingStatus.CANDIDATE, INSPECTOR)
        is FindingStatus.CANDIDATE
    )


def test_not_applicable_cannot_become_violation() -> None:
    with pytest.raises(TransitionError):
        advance_finding(
            FindingStatus.NOT_APPLICABLE, FindingStatus.CONFIRMED_VIOLATION, INSPECTOR
        )


def test_confirmed_violation_is_terminal() -> None:
    with pytest.raises(TransitionError):
        advance_finding(
            FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED, INSPECTOR
        )


def test_finalized_process_has_no_outgoing_transitions() -> None:
    for target in ProcessState:
        with pytest.raises(TransitionError):
            advance_process(ProcessState.FINALIZED, target)


def test_unfinalize_requires_supervisor_and_finalized() -> None:
    supervisor = Actor("admin", is_human=True, is_supervisor=True)
    with pytest.raises(TransitionError):
        unfinalize(ProcessState.FINALIZED, INSPECTOR)
    with pytest.raises(TransitionError):
        unfinalize(ProcessState.VERIFYING, supervisor)
    assert unfinalize(ProcessState.FINALIZED, supervisor) is ProcessState.COMPLETED


def test_upload_returns_process_to_parsing() -> None:
    assert advance_process(ProcessState.VERIFYING, ProcessState.PARSING) is ProcessState.PARSING
