"""Run the PostgreSQL → RabbitMQ outbox relay.

Publisher confirm means broker acceptance, not Rin acknowledgement. Delivery is
at-least-once; the stable event_id is the downstream inbox deduplication key.
"""

from __future__ import annotations

import os
import signal
import sys
from threading import Event

import psycopg

from kontur.infrastructure.broker import RabbitMqConfirmedPublisher
from kontur.infrastructure.outbox_worker import (
    OutboxRelayWorker,
    RelayWorkerSettings,
)


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def main() -> int:
    dsn = os.environ.get("KONTUR_DB_URL")
    amqp = os.environ.get("KONTUR_AMQP_URL")
    if not dsn or not amqp:
        print("KONTUR_DB_URL and KONTUR_AMQP_URL are required", file=sys.stderr)
        return 2

    try:
        settings = RelayWorkerSettings(
            poll_seconds=_positive_float("KONTUR_OUTBOX_POLL_SECONDS", 1.0),
            error_seconds=_positive_float("KONTUR_OUTBOX_ERROR_SECONDS", 5.0),
        )
        publisher = RabbitMqConfirmedPublisher(
            amqp,
            timeout_seconds=_positive_float("KONTUR_AMQP_TIMEOUT_SECONDS", 10.0),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    worker = OutboxRelayWorker(
        lambda: psycopg.connect(dsn),
        publisher,
        settings=settings,
        logger=lambda message: print(message, flush=True),
    )

    if os.environ.get("KONTUR_OUTBOX_ONCE", "").lower() in {"1", "true", "yes"}:
        result = worker.run_once()
        print("outbox empty" if result is None else result)
        return 0

    stopped = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    worker.run_forever(stopped.is_set)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
