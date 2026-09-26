"""Машины состояний. Запрещённые переходы ловятся здесь, а не в UI (ADR-0005)."""

from __future__ import annotations

from dataclasses import dataclass

from kontur.domain.statuses import (
    HUMAN_ONLY_STATUSES,
    FindingStatus,
    ProcessState,
    SyncState,
)


class TransitionError(RuntimeError):
    """Недопустимый переход. Наружу отдаётся как HTTP 409."""


PROCESS_TRANSITIONS: dict[ProcessState, frozenset[ProcessState]] = {
    ProcessState.PENDING: frozenset({ProcessState.PARSING}),
    ProcessState.PARSING: frozenset({ProcessState.READY, ProcessState.PENDING}),
    ProcessState.READY: frozenset({ProcessState.VERIFYING, ProcessState.PARSING}),
    # Дозагрузка до финализации возвращает процесс в PARSING (ТЗ п. 9.1).
    ProcessState.VERIFYING: frozenset({ProcessState.COMPLETED, ProcessState.PARSING}),
    # FINALIZED только через finalize_process: автомат и фоновая задача
    # не имеют права закрыть протокол обходом машины.
    ProcessState.COMPLETED: frozenset({ProcessState.PARSING}),
    # Из FINALIZED выход только через отмену финализации супервизором.
    ProcessState.FINALIZED: frozenset(),
}

FINDING_TRANSITIONS: dict[FindingStatus, frozenset[FindingStatus]] = {
    FindingStatus.CANDIDATE: frozenset(
        {
            FindingStatus.CONFIRMED_VIOLATION,
            FindingStatus.NEGATIVE_VERIFIED,
            FindingStatus.CLARIFICATION_REQUIRED,
        }
    ),
    FindingStatus.CLARIFICATION_REQUIRED: frozenset(
        {
            FindingStatus.CANDIDATE,
            FindingStatus.CONFIRMED_VIOLATION,
            FindingStatus.NEGATIVE_VERIFIED,
        }
    ),
    FindingStatus.SUSPICION: frozenset({FindingStatus.CANDIDATE}),
    FindingStatus.AUTO_NO_DIFFERENCE: frozenset({FindingStatus.NEGATIVE_VERIFIED}),
    # Статусы качества данных закрываются дозагрузкой, а не решением по существу.
    FindingStatus.MISSING_EVIDENCE: frozenset({FindingStatus.CANDIDATE}),
    FindingStatus.NOT_COMPARABLE: frozenset({FindingStatus.CANDIDATE}),
    FindingStatus.LOW_QUALITY: frozenset({FindingStatus.CANDIDATE}),
    FindingStatus.ABSTAIN: frozenset({FindingStatus.CANDIDATE}),
    FindingStatus.NOT_APPLICABLE: frozenset({FindingStatus.CANDIDATE}),
    FindingStatus.CONFIRMED_VIOLATION: frozenset(),
    FindingStatus.NEGATIVE_VERIFIED: frozenset(),
}

SYNC_TRANSITIONS: dict[SyncState, frozenset[SyncState]] = {
    SyncState.NOT_REQUESTED: frozenset({SyncState.PENDING_SYNC}),
    SyncState.PENDING_SYNC: frozenset({SyncState.SYNCING}),
    SyncState.SYNCING: frozenset(
        {
            SyncState.SYNCED,
            SyncState.RETRY_WAIT,
            SyncState.FAILED_TERMINAL,
            # Transport exhaustion returns the process to a human retry. SYNCED
            # remains reserved for a later Rin business ACK, not broker confirm.
            SyncState.PENDING_SYNC,
        }
    ),
    SyncState.RETRY_WAIT: frozenset({SyncState.SYNCING, SyncState.FAILED_TERMINAL}),
    SyncState.SYNCED: frozenset(),
    SyncState.FAILED_TERMINAL: frozenset({SyncState.PENDING_SYNC}),
}


@dataclass(frozen=True, slots=True)
class Actor:
    """Кто выполняет переход. Машина не принимает решения за человека."""

    actor_id: str
    is_human: bool
    is_supervisor: bool = False


def enter_verifying(current: ProcessState, actor: Actor) -> ProcessState:
    """Единственный легальный вход в VERIFYING. Без человека не вызывается."""

    if not actor.is_human:
        raise TransitionError("start verification requires a human inspector")
    if current is not ProcessState.READY:
        raise TransitionError(f"process: {current} -> VERIFYING")
    return ProcessState.VERIFYING


def enter_completed(current: ProcessState, actor: Actor) -> ProcessState:
    """Единственный легальный вход в COMPLETED. Без человека не вызывается."""

    if not actor.is_human:
        raise TransitionError("complete verification requires a human inspector")
    if current is not ProcessState.VERIFYING:
        raise TransitionError(f"process: {current} -> COMPLETED")
    return ProcessState.COMPLETED


def enter_finalized(current: ProcessState, actor: Actor) -> ProcessState:
    """Единственный легальный вход в FINALIZED. Без человека не вызывается."""

    if not actor.is_human:
        raise TransitionError("finalize requires a human inspector")
    if current is not ProcessState.COMPLETED:
        raise TransitionError(f"process: {current} -> FINALIZED")
    return ProcessState.FINALIZED


def advance_process(current: ProcessState, target: ProcessState) -> ProcessState:
    """Обычные переходы процесса. Очередь и финализация — только с актором."""

    if target is ProcessState.VERIFYING:
        raise TransitionError("VERIFYING только через start_verification с актором")
    if target is ProcessState.COMPLETED:
        raise TransitionError("COMPLETED только через complete_verification с актором и находками")
    if target is ProcessState.FINALIZED:
        raise TransitionError("FINALIZED только через finalize_process с актором и находками")
    if target not in PROCESS_TRANSITIONS[current]:
        raise TransitionError(f"process: {current} -> {target}")
    return target


def advance_finding(
    current: FindingStatus,
    target: FindingStatus,
    actor: Actor,
) -> FindingStatus:
    """Переход статуса находки.

    Инвариант ADR-0001: CONFIRMED_VIOLATION и NEGATIVE_VERIFIED присваивает
    только человек. Автомат, LLM и фоновая задача получают отказ.
    """

    if target in HUMAN_ONLY_STATUSES and not actor.is_human:
        raise TransitionError(f"finding: {target} requires a human inspector, got {actor.actor_id}")
    # ТЗ п. 9.2: инспектор может подтвердить применимость. Автомат — нет.
    if current is FindingStatus.NOT_APPLICABLE and not actor.is_human:
        raise TransitionError("NOT_APPLICABLE override requires a human inspector")
    if target not in FINDING_TRANSITIONS[current]:
        raise TransitionError(f"finding: {current} -> {target}")
    return target


def advance_sync(current: SyncState, target: SyncState) -> SyncState:
    if target not in SYNC_TRANSITIONS[current]:
        raise TransitionError(f"sync: {current} -> {target}")
    return target


def unfinalize(current: ProcessState, actor: Actor, reason: str) -> ProcessState:
    """Отмена финализации: инспектор, администратор или супервизор.

    Только из FINALIZED и только с причиной. Машина этот переход не делает.
    Новая версия протокола и запись аудита — обязанность вызывающего слоя.
    """

    if current is not ProcessState.FINALIZED:
        raise TransitionError("unfinalize requires FINALIZED")
    if not actor.is_human:
        raise TransitionError("unfinalize requires a human")
    if not reason.strip():
        raise TransitionError("unfinalize requires reason")
    return ProcessState.COMPLETED
