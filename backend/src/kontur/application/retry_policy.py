"""Политики повторов: разбор пакета (ТЗ п. 9.1) и передача в РиН (ТЗ п. 9.6).

Числа из ТЗ («до двух повторов», «1, 5, 15 минут») до сих пор жили только в
тексте документации. Здесь они становятся кодом с одним свойством: повторы
конечны, а исчерпание повторов обязано порождать уведомление администратора,
а не молчаливую потерю процесса.
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.domain.statuses import SyncState

#: ТЗ п. 9.1: после таймаута разбор повторяется не более двух раз.
MAX_PARSE_RETRIES: int = 2

#: Паузы перед повторами разбора, сек.
PARSE_BACKOFF_SECONDS: tuple[int, ...] = (30, 120)

#: ТЗ п. 9.6: три повтора передачи через 1, 5 и 15 минут.
SYNC_BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 900)
MAX_SYNC_RETRIES: int = len(SYNC_BACKOFF_SECONDS)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    attempts_done: int
    retry: bool
    delay_seconds: int | None
    notify_admin: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SyncRetryDecision:
    attempts_done: int
    retry: bool
    delay_seconds: int | None
    notify_admin: bool
    state: SyncState
    reason: str


def _validate(attempts_done: int) -> None:
    if attempts_done < 1:
        raise ValueError("повтор считается от первой завершившейся попытки (attempts_done ≥ 1)")


def next_parse_attempt(
    attempts_done: int,
    *,
    max_retries: int = MAX_PARSE_RETRIES,
    backoff: tuple[int, ...] = PARSE_BACKOFF_SECONDS,
) -> RetryDecision:
    """Таймаут разбора: до `max_retries` повторов, затем уведомление администратора."""

    _validate(attempts_done)
    if attempts_done > max_retries:
        return RetryDecision(
            attempts_done=attempts_done,
            retry=False,
            delay_seconds=None,
            notify_admin=True,
            reason=f"исчерпаны {max_retries} повтора разбора (ТЗ п. 9.1)",
        )
    delay = backoff[min(attempts_done - 1, len(backoff) - 1)]
    return RetryDecision(
        attempts_done=attempts_done,
        retry=True,
        delay_seconds=delay,
        notify_admin=False,
        reason=f"повтор {attempts_done} из {max_retries} через {delay} с",
    )


def next_sync_attempt(attempts_done: int) -> SyncRetryDecision:
    """Передача в РиН: 1, 5, 15 минут, затем PENDING_SYNC и уведомление.

    Терминальным отказом сбой связи не делается: решение инспектора уже
    принято, протокол финализирован, и повторная отправка остаётся возможной.
    """

    _validate(attempts_done)
    if attempts_done > MAX_SYNC_RETRIES:
        return SyncRetryDecision(
            attempts_done=attempts_done,
            retry=False,
            delay_seconds=None,
            notify_admin=True,
            state=SyncState.PENDING_SYNC,
            reason="исчерпаны 3 повтора передачи; протокол ждёт ручной отправки (ТЗ п. 9.6)",
        )
    delay = SYNC_BACKOFF_SECONDS[attempts_done - 1]
    return SyncRetryDecision(
        attempts_done=attempts_done,
        retry=True,
        delay_seconds=delay,
        notify_admin=False,
        state=SyncState.RETRY_WAIT,
        reason=f"повтор {attempts_done} из {MAX_SYNC_RETRIES} через {delay // 60} мин",
    )
