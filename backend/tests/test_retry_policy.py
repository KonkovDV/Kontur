"""retry_policy.py: таблица решений next_parse_attempt / next_sync_attempt."""

from __future__ import annotations

import pytest

from kontur.application.retry_policy import (
    MAX_PARSE_RETRIES,
    MAX_SYNC_RETRIES,
    PARSE_BACKOFF_SECONDS,
    SYNC_BACKOFF_SECONDS,
    next_parse_attempt,
    next_sync_attempt,
)
from kontur.domain.statuses import SyncState


class TestNextParseAttempt:
    def test_zero_attempts_raises(self) -> None:
        with pytest.raises(ValueError, match="attempts_done"):
            next_parse_attempt(0)

    def test_first_attempt_retry_true(self) -> None:
        d = next_parse_attempt(1)
        assert d.retry is True
        assert d.notify_admin is False
        assert d.delay_seconds == PARSE_BACKOFF_SECONDS[0]

    def test_second_attempt_retry_true(self) -> None:
        d = next_parse_attempt(2)
        assert d.retry is True
        assert d.delay_seconds == PARSE_BACKOFF_SECONDS[1]

    def test_exhausted_retry_false(self) -> None:
        d = next_parse_attempt(MAX_PARSE_RETRIES + 1)
        assert d.retry is False
        assert d.notify_admin is True
        assert d.delay_seconds is None

    def test_attempts_done_stored(self) -> None:
        assert next_parse_attempt(1).attempts_done == 1
        assert next_parse_attempt(2).attempts_done == 2

    @pytest.mark.parametrize("n", range(1, MAX_PARSE_RETRIES + 1))
    def test_all_retries_have_positive_delay(self, n: int) -> None:
        d = next_parse_attempt(n)
        assert d.retry is True
        assert isinstance(d.delay_seconds, int) and d.delay_seconds > 0


class TestNextSyncAttempt:
    def test_zero_attempts_raises(self) -> None:
        with pytest.raises(ValueError):
            next_sync_attempt(0)

    @pytest.mark.parametrize("n,delay", list(enumerate(SYNC_BACKOFF_SECONDS, start=1)))
    def test_backoff_table(
        self, n: int, delay: int
    ) -> None:
        d = next_sync_attempt(n)
        assert d.retry is True
        assert d.delay_seconds == delay
        assert d.state is SyncState.RETRY_WAIT
        assert d.notify_admin is False

    def test_exhausted_goes_pending_sync(self) -> None:
        d = next_sync_attempt(MAX_SYNC_RETRIES + 1)
        assert d.retry is False
        assert d.notify_admin is True
        assert d.state is SyncState.PENDING_SYNC
        assert d.delay_seconds is None

    def test_max_sync_retries_constant(self) -> None:
        """ТЗ п. 9.6: именно 3 повтора."""
        assert MAX_SYNC_RETRIES == 3

    def test_backoff_minutes_match_tz(self) -> None:
        """ТЗ п. 9.6: 1, 5, 15 минут."""
        assert SYNC_BACKOFF_SECONDS == (60, 300, 900)
