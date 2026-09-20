"""Consume the protocol queue into the transactional inbox.

Manual consumer ACK happens only after the PostgreSQL commit. This is not a Rin
business acknowledgement and does not mark the process as synchronized.
"""

from __future__ import annotations

import asyncio
import os
import sys
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
    header_str,
    settle_inbox_delivery,
)
from kontur.infrastructure.outbox import ROUTING_KEY


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _redelivery_count(message: Any) -> int:
    headers = message.headers or {}
    raw = headers.get("x-delivery-count", 1)
    try:
        count = int(raw)
    except (TypeError, ValueError):
        count = 1
    return count if count > 0 else 1


async def consume_once(dsn: str, amqp_url: str) -> str:
    import aio_pika  # type: ignore[import-not-found,import-untyped,unused-ignore]
    from aio_pika import ExchangeType  # type: ignore[import-not-found,import-untyped,unused-ignore]

    connection = await aio_pika.connect_robust(amqp_url)
    async with connection:
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
        incoming = await queue.get(fail=False, timeout=5)
        if incoming is None:
            return "empty"
        headers = incoming.headers or {}
        delivery = BrokerDelivery(
            event_id=str(incoming.message_id or header_str(headers, "event_id")),
            process_id=header_str(headers, "process_id"),
            protocol_id=header_str(headers, "protocol_id"),
            payload_sha256=header_str(headers, "payload_sha256"),
            body=bytes(incoming.body),
            redelivery_count=_redelivery_count(incoming),
            delivery_tag=str(incoming.delivery_tag),
        )

        class _Channel:
            def ack(self, delivery_tag: str) -> None:
                del delivery_tag
                incoming.ack()

            def nack(self, delivery_tag: str, *, requeue: bool) -> None:
                del delivery_tag
                incoming.nack(requeue=requeue)

        with psycopg.connect(dsn) as db:
            return settle_inbox_delivery(db, delivery, _Channel())


def main() -> int:
    try:
        dsn = _require_env("KONTUR_DB_URL")
        amqp = _require_env("KONTUR_AMQP_URL")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        result = asyncio.run(consume_once(dsn, amqp))
    except Exception as exc:
        print(f"inbox consume error: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("inbox empty" if result == "empty" else result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
