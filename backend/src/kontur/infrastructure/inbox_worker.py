"""Long-running inbox consumer session supervisor.

A processing or settlement exception invalidates the AMQP session. The caller
must close it so RabbitMQ can automatically requeue any unsettled delivery;
the next supervised session reconnects after bounded backoff.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

ConsumeSession = Callable[[], Awaitable[None]]
AsyncSleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class InboxWorkerSettings:
    empty_seconds: float = 1.0
    error_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.empty_seconds) or self.empty_seconds <= 0:
            raise ValueError("empty_seconds must be finite and positive")
        if not math.isfinite(self.error_seconds) or self.error_seconds <= 0:
            raise ValueError("error_seconds must be finite and positive")


class InboxConsumerWorker:
    """Supervise whole AMQP sessions and log exception types only."""

    def __init__(
        self,
        consume_session: ConsumeSession,
        *,
        settings: InboxWorkerSettings | None = None,
        sleeper: AsyncSleeper | None = None,
        logger: Callable[[str], None] = print,
    ) -> None:
        self._consume_session = consume_session
        self._settings = settings or InboxWorkerSettings()
        self._sleep = sleeper or asyncio.sleep
        self._log = logger

    async def run_forever(self, stop_requested: Callable[[], bool]) -> None:
        while not stop_requested():
            delay = self._settings.empty_seconds
            try:
                await self._consume_session()
                if stop_requested():
                    return
                self._log("inbox session ended; reconnecting")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log(f"inbox consume error: {type(exc).__name__}")
                delay = self._settings.error_seconds
            if not stop_requested():
                await self._sleep(delay)
