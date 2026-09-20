"""Consume the protocol queue into the transactional inbox.

Manual consumer ACK is awaited only after the PostgreSQL commit. Default mode is
a long-running push consumer. This is not a Rin business acknowledgement.
"""

from __future__ import annotations

import asyncio
import math
import os
import signal
import sys
from collections.abc import Callable
from typing import Any

import psycopg

from kontur.infrastructure.broker import (
    DEAD_LETTER_EXCHANGE,
    DEAD_LETTER_QUEUE,
    PREFETCH_COUNT,
    protocol_queue_arguments,
)
from kontur.infrastructure.inbox import (
    BrokerDelivery,
    delivery_attempt,
    header_str,
    settle_async_inbox_delivery,
)
from kontur.infrastructure.inbox_worker import InboxConsumerWorker, InboxWorkerSettings
from kontur.infrastructure.outbox import ROUTING_KEY


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _broker_delivery(incoming: Any) -> BrokerDelivery:
    headers = incoming.headers or {}
    return BrokerDelivery(
        event_id=str(incoming.message_id or header_str(headers, "event_id")),
        process_id=header_str(headers, "process_id"),
        protocol_id=header_str(headers, "protocol_id"),
        payload_sha256=header_str(headers, "payload_sha256"),
        body=bytes(incoming.body),
        redelivery_count=delivery_attempt(headers),
        delivery_tag=str(incoming.delivery_tag),
    )


async def _settle(incoming: Any, dsn: str) -> str:
    delivery = _broker_delivery(incoming)
    with psycopg.connect(dsn) as db:
        return await settle_async_inbox_delivery(db, delivery, incoming)


async def _open_queue(amqp_url: str) -> Any:
    import aio_pika  # type: ignore[import-not-found,import-untyped,unused-ignore]
    from aio_pika import ExchangeType  # type: ignore[import-not-found,import-untyped,unused-ignore]

    connection = await aio_pika.connect_robust(amqp_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=PREFETCH_COUNT)
    await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE,
        ExchangeType.FANOUT,
        durable=True,
    )
    poison = await channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
    await poison.bind(DEAD_LETTER_EXCHANGE)
    queue = await channel.declare_queue(
        ROUTING_KEY,
        durable=True,
        arguments=protocol_queue_arguments(),
    )
    return connection, queue


async def consume_once(dsn: str, amqp_url: str, *, timeout_seconds: float = 5.0) -> str:
    connection, queue = await _open_queue(amqp_url)
    try:
        incoming = await queue.get(fail=False, timeout=timeout_seconds)
        if incoming is None:
            return "empty"
        return await _settle(incoming, dsn)
    finally:
        await connection.close()


async def _next_or_stop(iterator: Any, stop: asyncio.Event) -> Any | None:
    delivery_task = asyncio.create_task(iterator.__anext__())
    stop_task = asyncio.create_task(stop.wait())
    done, _pending = await asyncio.wait(
        {delivery_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if stop_task in done:
        delivery_task.cancel()
        await asyncio.gather(delivery_task, return_exceptions=True)
        return None
    stop_task.cancel()
    await asyncio.gather(stop_task, return_exceptions=True)
    return delivery_task.result()


async def _consume_session(
    dsn: str,
    amqp_url: str,
    stop: asyncio.Event,
) -> None:
    connection, queue = await _open_queue(amqp_url)
    try:
        async with queue.iterator() as iterator:
            while not stop.is_set():
                incoming = await _next_or_stop(iterator, stop)
                if incoming is None:
                    return
                # Any DB or settlement exception escapes the session. Closing the
                # connection below lets RabbitMQ requeue only if settlement was
                # not accepted; inbox event_id makes a redelivery idempotent.
                await _settle(incoming, dsn)
    finally:
        await connection.close()


async def consume_forever(
    dsn: str,
    amqp_url: str,
    stop: asyncio.Event,
    settings: InboxWorkerSettings,
    logger: Callable[[str], None],
) -> None:
    async def run_session() -> None:
        await _consume_session(dsn, amqp_url, stop)

    worker = InboxConsumerWorker(
        run_session,
        settings=settings,
        logger=logger,
    )
    await worker.run_forever(stop.is_set)


def main() -> int:
    try:
        dsn = _require_env("KONTUR_DB_URL")
        amqp = _require_env("KONTUR_AMQP_URL")
        settings = InboxWorkerSettings(
            empty_seconds=_positive_float("KONTUR_INBOX_EMPTY_SECONDS", 1.0),
            error_seconds=_positive_float("KONTUR_INBOX_ERROR_SECONDS", 5.0),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    def log(message: str) -> None:
        print(message, flush=True)

    if os.environ.get("KONTUR_INBOX_ONCE", "").lower() in {"1", "true", "yes"}:
        try:
            result = asyncio.run(consume_once(dsn, amqp))
        except Exception as exc:
            print(f"inbox consume error: {type(exc).__name__}", file=sys.stderr)
            return 1
        print("inbox empty" if result == "empty" else result)
        return 0

    async def _run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_stop() -> None:
            stop.set()

        try:
            loop.add_signal_handler(signal.SIGTERM, request_stop)
            loop.add_signal_handler(signal.SIGINT, request_stop)
        except NotImplementedError:
            signal.signal(signal.SIGTERM, lambda _s, _f: loop.call_soon_threadsafe(stop.set))
            signal.signal(signal.SIGINT, lambda _s, _f: loop.call_soon_threadsafe(stop.set))
        await consume_forever(dsn, amqp, stop, settings, log)

    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"inbox consume error: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
