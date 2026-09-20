"""Inbox session supervisor reconnects safely without leaking secrets."""

from __future__ import annotations

import asyncio

import pytest

from kontur.infrastructure.inbox_worker import (
    InboxConsumerWorker,
    InboxWorkerSettings,
)


def test_clean_stop_after_session_has_no_reconnect_delay() -> None:
    delays: list[float] = []
    messages: list[str] = []
    stopped = False

    async def session() -> None:
        nonlocal stopped
        stopped = True

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    worker = InboxConsumerWorker(
        session,
        settings=InboxWorkerSettings(empty_seconds=0.25, error_seconds=3.0),
        sleeper=sleeper,
        logger=messages.append,
    )
    asyncio.run(worker.run_forever(lambda: stopped))
    assert messages == []
    assert delays == []


def test_unexpected_clean_session_end_reconnects_with_backoff() -> None:
    delays: list[float] = []
    messages: list[str] = []
    stopped = False

    async def session() -> None:
        return None

    async def sleeper(delay: float) -> None:
        nonlocal stopped
        delays.append(delay)
        stopped = True

    worker = InboxConsumerWorker(
        session,
        settings=InboxWorkerSettings(empty_seconds=0.5, error_seconds=3.0),
        sleeper=sleeper,
        logger=messages.append,
    )
    asyncio.run(worker.run_forever(lambda: stopped))
    assert delays == [0.5]
    assert messages == ["inbox session ended; reconnecting"]


def test_session_error_reconnects_and_logs_type_without_secret() -> None:
    delays: list[float] = []
    messages: list[str] = []
    stopped = False

    async def session() -> None:
        raise RuntimeError("postgresql://user:secret@example.invalid/db")

    async def sleeper(delay: float) -> None:
        nonlocal stopped
        delays.append(delay)
        stopped = True

    worker = InboxConsumerWorker(
        session,
        settings=InboxWorkerSettings(empty_seconds=0.25, error_seconds=4.0),
        sleeper=sleeper,
        logger=messages.append,
    )
    asyncio.run(worker.run_forever(lambda: stopped))
    assert delays == [4.0]
    assert messages == ["inbox consume error: RuntimeError"]
    assert "secret" not in messages[0]


def test_cancelled_session_is_not_swallowed() -> None:
    async def session() -> None:
        raise asyncio.CancelledError

    worker = InboxConsumerWorker(session)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker.run_forever(lambda: False))


def test_worker_settings_reject_busy_loops_and_non_finite() -> None:
    with pytest.raises(ValueError, match="empty_seconds"):
        InboxWorkerSettings(empty_seconds=0)
    with pytest.raises(ValueError, match="error_seconds"):
        InboxWorkerSettings(error_seconds=float("nan"))
    with pytest.raises(ValueError, match="error_seconds"):
        InboxWorkerSettings(error_seconds=float("inf"))
