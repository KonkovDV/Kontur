"""Hardened RabbitMQ publisher for the transactional outbox relay.

A publisher confirm proves only that RabbitMQ accepted the persistent message.
It is not a Rin acknowledgement and does not provide exactly-once effects.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from kontur.infrastructure.outbox import ROUTING_KEY, PublishError

DEFAULT_TIMEOUT_SECONDS = 10.0
PREFETCH_COUNT = 1
DELIVERY_LIMIT = 4
DEAD_LETTER_EXCHANGE = "kontur.rin.dlx"
DEAD_LETTER_QUEUE = "kontur.rin.protocol.poison"


def protocol_queue_arguments() -> dict[str, object]:
    """Quorum queue with a bounded redelivery limit and DLX.

    Existing classic/quorum queues without these arguments must be deleted
    before declare, otherwise RabbitMQ raises PRECONDITION_FAILED.
    """

    return {
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        "x-delivery-limit": DELIVERY_LIMIT,
    }


class RabbitMqConfirmedPublisher:
    """Publish persistent messages to a durable quorum queue with confirms."""

    def __init__(self, url: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        if not url.strip():
            raise ValueError("RabbitMQ URL is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._url = url
        self._timeout_seconds = timeout_seconds

    def publish_confirmed(
        self,
        *,
        event_id: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> None:
        asyncio.run(self._publish(event_id, body, dict(headers)))

    async def _publish(
        self,
        event_id: str,
        body: bytes,
        headers: dict[str, str],
    ) -> None:
        try:
            import aio_pika  # type: ignore[import-not-found,import-untyped,unused-ignore]
            from aio_pika import (  # type: ignore[import-not-found,import-untyped,unused-ignore]
                DeliveryMode,
                Message,
            )
        except ImportError as exc:
            raise PublishError("aio-pika is not installed") from exc

        try:
            connection = await aio_pika.connect_robust(
                self._url,
                timeout=self._timeout_seconds,
            )
            async with connection:
                channel = await connection.channel(
                    publisher_confirms=True,
                    on_return_raises=True,
                )
                await channel.declare_queue(
                    ROUTING_KEY,
                    durable=True,
                    arguments=protocol_queue_arguments(),
                    timeout=self._timeout_seconds,
                )
                confirmation = await channel.default_exchange.publish(
                    Message(
                        body,
                        message_id=event_id,
                        delivery_mode=DeliveryMode.PERSISTENT,
                        headers=headers,
                        content_type="application/json",
                        content_encoding="utf-8",
                    ),
                    routing_key=ROUTING_KEY,
                    mandatory=True,
                    timeout=self._timeout_seconds,
                )
                if confirmation is False:
                    raise PublishError("RabbitMQ rejected the message")
        except PublishError:
            raise
        except Exception as exc:
            raise PublishError(f"RabbitMQ publish failed: {type(exc).__name__}") from exc
