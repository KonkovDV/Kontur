"""Bounded polling worker for PostgreSQL outbox delivery.

Each cycle owns one database connection and transaction. A broker publish and
its DELIVERED/PENDING state transition commit together. A crash after broker
accept but before commit intentionally causes at-least-once redelivery with the
same event_id; downstream consumers must deduplicate it in an inbox.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import sleep
from typing import Protocol

from kontur.infrastructure.outbox import OutboxPublisher, relay_once_postgres


class RelayConnection(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


RelayCycle = Callable[[object, OutboxPublisher, datetime | None], str | None]
ConnectionFactory = Callable[[], RelayConnection]


@dataclass(frozen=True, slots=True)
class RelayWorkerSettings:
    poll_seconds: float = 1.0
    error_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self.error_seconds <= 0:
            raise ValueError("error_seconds must be positive")


class OutboxRelayWorker:
    """Long-running fail-closed relay with explicit transaction ownership."""

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        publisher: OutboxPublisher,
        *,
        settings: RelayWorkerSettings | None = None,
        relay_cycle: RelayCycle = relay_once_postgres,
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = sleep,
        logger: Callable[[str], None] = print,
    ) -> None:
        self._connection_factory = connection_factory
        self._publisher = publisher
        self._settings = settings or RelayWorkerSettings()
        self._relay_cycle = relay_cycle
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._sleep = sleeper
        self._log = logger

    def run_once(self) -> str | None:
        connection = self._connection_factory()
        try:
            result = self._relay_cycle(connection, self._publisher, self._now())
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def run_forever(self, stop_requested: Callable[[], bool]) -> None:
        while not stop_requested():
            try:
                result = self.run_once()
                if result is not None:
                    self._log(f"outbox relay: {result}")
                delay = self._settings.poll_seconds
            except Exception as exc:
                self._log(f"outbox relay error: {type(exc).__name__}")
                delay = self._settings.error_seconds
            if not stop_requested():
                self._sleep(delay)
