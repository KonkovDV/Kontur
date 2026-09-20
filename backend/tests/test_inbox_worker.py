"""Inbox consumer loop owns backoff and never leaks secret text."""

from __future__ import annotations

import asyncio

import pytest

from kontur.infrastructure.inbox_worker import (
    InboxConsumerWorker,
    InboxWorkerSettings,
)


def test_successful_message_is_logged_without_empty_backoff() -> None:
    delays: list[float] = []
    messages: list[str] = []
    stopped = False

    async def consume() -> str:
        nonlocal stopped
        stopped = True
        return "ACK"

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    worker = InboxConsumerWorker(
        consume,
        settings=InboxWorkerSettings(empty_seconds=0.25, error_seconds=3.0),
        sleeper=sleeper,
        logger=messages.append,
    )
    asyncio.run(worker.run_forever(lambda: stopped))
    assert messages == ["inbox consume: ACK"]
    assert delays == []


def test_empty_queue_backs_off_without_success_log() -> None:
    delays: list[float] = []
    messages: list[str] = []
    stopped = False

    async def consume() -> str:
        return "empty"

    async def sleeper(delay: float) -> None:
        nonlocal stopped
        delays.append(delay)
        stopped = True

    worker = InboxConsumerWorker(
        consume,
        settings=InboxWorkerSettings(empty_seconds=0.5, error_seconds=3.0),
        sleeper=sleeper,
        logger=messages.append,
    )
    asyncio.run(worker.run_forever(lambda: stopped))
    assert delays == [0.5]
    assert messages == []


def test_error_backs_off_and_logs_type_without_secret() -> None:
    delays: list[float] = []
    messages: list[str] = []
    stopped = False

    async def consume() -> str:
        raise RuntimeError("postgresql://user:secret@example.invalid/db")

    async def sleeper(delay: float) -> None:
        nonlocal stopped
        delays.append(delay)
        stopped = True

    worker = InboxConsumerWorker(
        consume,
        settings=InboxWorkerSettings(empty_seconds=0.25, error_seconds=4.0),
        sleeper=sleeper,
        logger=messages.append,
    )
    asyncio.run(worker.run_forever(lambda: stopped))
    assert delays == [4.0]
    assert messages == ["inbox consume error: RuntimeError"]
    assert "secret" not in messages[0]


def test_worker_settings_reject_busy_loops_and_non_finite() -> None:
    with pytest.raises(ValueError, match="empty_seconds"):
        InboxWorkerSettings(empty_seconds=0)
    with pytest.raises(ValueError, match="error_seconds"):
        InboxWorkerSettings(error_seconds=float("nan"))
    with pytest.raises(ValueError, match="error_seconds"):
        InboxWorkerSettings(error_seconds=float("inf"))
