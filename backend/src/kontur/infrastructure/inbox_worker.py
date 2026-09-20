"""Long-running inbox consumer loop.

PostgreSQL persistence stays in persist_inbox_delivery. Broker ACK/NACK is
awaited only after commit. This worker does not mark a process synchronized.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

ConsumeOne = Callable[[], Awaitable[str]]
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
    """Fail-closed loop: log exception types only, never DSN text."""

    def __init__(
        self,
        consume_one: ConsumeOne,
        *,
        settings: InboxWorkerSettings | None = None,
        sleeper: AsyncSleeper | None = None,
        logger: Callable[[str], None] = print,
        sleep_on_empty: bool = True,
    ) -> None:
        self._consume_one = consume_one
        self._settings = settings or InboxWorkerSettings()
        self._sleep = sleeper
        self._log = logger
        self._sleep_on_empty = sleep_on_empty

    async def run_once(self) -> str:
        return await self._consume_one()

    async def run_forever(self, stop_requested: Callable[[], bool]) -> None:
        while not stop_requested():
            delay = 0.0
            try:
                result = await self.run_once()
                if result != "empty":
                    self._log(f"inbox consume: {result}")
                elif self._sleep_on_empty:
                    delay = self._settings.empty_seconds
            except Exception as exc:
                self._log(f"inbox consume error: {type(exc).__name__}")
                delay = self._settings.error_seconds
            if delay > 0 and not stop_requested() and self._sleep is not None:
                await self._sleep(delay)
            elif delay > 0 and not stop_requested():
                await asyncio.sleep(delay)
