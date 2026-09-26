"""Инварианты машин состояний. Падение любого теста — дефект класса S0."""

from __future__ import annotations

import pytest

from kontur.domain.state_machines import (
    FINDING_TRANSITIONS,
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


def test_enter_finalized_requires_human() -> None:
    from kontur.domain.state_machines import enter_finalized

    with pytest.raises(TransitionError, match="human"):
        enter_finalized(ProcessState.COMPLETED, MACHINE)
    assert (
        enter_finalized(ProcessState.COMPLETED, INSPECTOR) is ProcessState.FINALIZED
    )
    with pytest.raises(TransitionError, match="finalize_process"):
        advance_process(ProcessState.COMPLETED, ProcessState.FINALIZED)


def test_finding_transitions_cover_every_status() -> None:
    assert set(FINDING_TRANSITIONS) == set(FindingStatus)


def test_unfinalize_requires_a_human_and_finalized() -> None:
    supervisor = Actor("lead", is_human=True, is_supervisor=True)
    with pytest.raises(TransitionError, match="human"):
        unfinalize(ProcessState.FINALIZED, MACHINE, "ошибочная финализация")
    with pytest.raises(TransitionError):
        unfinalize(ProcessState.VERIFYING, supervisor, "ошибочная финализация")
    with pytest.raises(TransitionError, match="reason"):
        unfinalize(ProcessState.FINALIZED, supervisor, "   ")
    assert (
        unfinalize(ProcessState.FINALIZED, INSPECTOR, "ошибочная финализация")
        is ProcessState.COMPLETED
    )
    assert (
        unfinalize(ProcessState.FINALIZED, supervisor, "ошибочная финализация")
        is ProcessState.COMPLETED
    )


def test_upload_returns_process_to_parsing() -> None:
    assert advance_process(ProcessState.VERIFYING, ProcessState.PARSING) is ProcessState.PARSING


def test_machine_cannot_open_or_close_queue_via_advance_process() -> None:
    with pytest.raises(TransitionError, match="start_verification"):
        advance_process(ProcessState.READY, ProcessState.VERIFYING)
    with pytest.raises(TransitionError, match="complete_verification"):
        advance_process(ProcessState.VERIFYING, ProcessState.COMPLETED)


def test_enter_verifying_and_completed_require_human() -> None:
    from kontur.domain.state_machines import enter_completed, enter_verifying

    with pytest.raises(TransitionError, match="human"):
        enter_verifying(ProcessState.READY, MACHINE)
    assert enter_verifying(ProcessState.READY, INSPECTOR) is ProcessState.VERIFYING
    with pytest.raises(TransitionError, match="human"):
        enter_completed(ProcessState.VERIFYING, MACHINE)
    assert enter_completed(ProcessState.VERIFYING, INSPECTOR) is ProcessState.COMPLETED
