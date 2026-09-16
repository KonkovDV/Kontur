"""Повторы конечны: два повтора разбора (п. 9.1), три повтора РиН 1/5/15 мин (п. 9.6)."""

from __future__ import annotations

import pytest
from kontur.application.retry_policy import (
    MAX_PARSE_RETRIES,
    SYNC_BACKOFF_SECONDS,
    next_parse_attempt,
    next_sync_attempt,
)
from kontur.domain.statuses import SyncState


def test_parse_retries_stop_after_two_and_notify_admin() -> None:
    first = next_parse_attempt(1)
    second = next_parse_attempt(2)
    third = next_parse_attempt(3)
    assert (first.retry, first.notify_admin) == (True, False)
    assert (second.retry, second.notify_admin) == (True, False)
    assert (third.retry, third.notify_admin) == (False, True)
    assert third.delay_seconds is None
    assert MAX_PARSE_RETRIES == 2


def test_parse_retry_delays_are_finite_and_growing() -> None:
    delays = [next_parse_attempt(attempt).delay_seconds for attempt in (1, 2)]
    assert delays == [30, 120]
    assert all(delay is not None and delay > 0 for delay in delays)


def test_sync_retries_follow_one_five_fifteen_minutes() -> None:
    assert SYNC_BACKOFF_SECONDS == (60, 300, 900)
    for attempt, delay in zip((1, 2, 3), SYNC_BACKOFF_SECONDS, strict=True):
        decision = next_sync_attempt(attempt)
        assert decision.retry
        assert decision.delay_seconds == delay
        assert decision.state is SyncState.RETRY_WAIT
        assert not decision.notify_admin


def test_exhausted_sync_waits_for_a_human_instead_of_dying() -> None:
    decision = next_sync_attempt(4)
    assert not decision.retry
    assert decision.notify_admin
    assert decision.state is SyncState.PENDING_SYNC
    assert decision.state is not SyncState.FAILED_TERMINAL
    assert next_sync_attempt(99).state is SyncState.PENDING_SYNC


def test_zero_attempts_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        next_parse_attempt(0)
    with pytest.raises(ValueError):
        next_sync_attempt(-1)
