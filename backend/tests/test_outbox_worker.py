"""Relay worker owns commit/rollback and never hides failed cycles."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kontur.infrastructure.outbox import RecordingPublisher
from kontur.infrastructure.outbox_worker import (
    OutboxRelayWorker,
    RelayWorkerSettings,
)


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


def _now() -> datetime:
    return datetime(2026, 9, 20, 18, 0, tzinfo=UTC)


def test_successful_cycle_commits_and_closes() -> None:
    connection = _Connection()
    seen: list[datetime | None] = []

    def relay(_connection: object, _publisher: object, now: datetime | None) -> str:
        seen.append(now)
        return "DELIVERED"

    worker = OutboxRelayWorker(
        lambda: connection,
        RecordingPublisher(),
        relay_cycle=relay,
        now=_now,
    )
    assert worker.run_once() == "DELIVERED"
    assert seen == [_now()]
    assert (connection.commits, connection.rollbacks, connection.closes) == (1, 0, 1)


def test_failed_cycle_rolls_back_closes_and_reraises() -> None:
    connection = _Connection()

    def relay(_connection: object, _publisher: object, _now: datetime | None) -> str:
        raise RuntimeError("database unavailable")

    worker = OutboxRelayWorker(
        lambda: connection,
        RecordingPublisher(),
        relay_cycle=relay,
        now=_now,
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        worker.run_once()
    assert (connection.commits, connection.rollbacks, connection.closes) == (0, 1, 1)


def test_forever_loop_backs_off_after_error_without_leaking_secret_text() -> None:
    connection = _Connection()
    stopped = False
    messages: list[str] = []
    delays: list[float] = []

    def relay(_connection: object, _publisher: object, _now: datetime | None) -> str:
        raise RuntimeError("postgresql://user:secret@example.invalid/db")

    def sleeper(delay: float) -> None:
        nonlocal stopped
        delays.append(delay)
        stopped = True

    worker = OutboxRelayWorker(
        lambda: connection,
        RecordingPublisher(),
        settings=RelayWorkerSettings(poll_seconds=0.25, error_seconds=3.0),
        relay_cycle=relay,
        now=_now,
        sleeper=sleeper,
        logger=messages.append,
    )
    worker.run_forever(lambda: stopped)
    assert delays == [3.0]
    assert messages == ["outbox relay error: RuntimeError"]
    assert "secret" not in messages[0]


def test_worker_settings_reject_busy_loops() -> None:
    with pytest.raises(ValueError, match="poll_seconds"):
        RelayWorkerSettings(poll_seconds=0)
    with pytest.raises(ValueError, match="error_seconds"):
        RelayWorkerSettings(error_seconds=-1)
