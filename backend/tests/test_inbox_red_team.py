"""Red-team regressions for real aio-pika settlement and poison duplicates."""

from __future__ import annotations

import asyncio

from kontur.infrastructure.inbox import (
    BrokerDelivery,
    delivery_attempt,
    payload_digest,
    settle_async_inbox_delivery,
)

BODY = b'{"object_id":"o-1","protocol_id":"protocol-p-1","version":1}'
SHA = payload_digest(BODY)


class _Cursor:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class _Connection:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.order: list[str] = []

    def execute(self, _sql: str, _params: dict[str, object]) -> _Cursor:
        self.order.append("insert")
        return _Cursor(None if self.duplicate else ("event-1",))

    def commit(self) -> None:
        self.order.append("commit")

    def rollback(self) -> None:
        self.order.append("rollback")


class _AsyncMessage:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.awaited = False

    async def ack(self) -> None:
        await asyncio.sleep(0)
        self.awaited = True
        self.order.append("ack")

    async def nack(self, *, requeue: bool) -> None:
        await asyncio.sleep(0)
        self.awaited = True
        self.order.append(f"nack:{str(requeue).lower()}")


def _delivery(*, bad_hash: bool = False, attempts: int = 1) -> BrokerDelivery:
    return BrokerDelivery(
        event_id="event-1",
        process_id="p-1",
        protocol_id="protocol-p-1",
        payload_sha256="b" * 64 if bad_hash else SHA,
        body=BODY,
        redelivery_count=attempts,
    )


def test_async_ack_is_awaited_strictly_after_commit() -> None:
    connection = _Connection()
    message = _AsyncMessage(connection.order)
    result = asyncio.run(
        settle_async_inbox_delivery(connection, _delivery(), message)
    )
    assert result == "ACK"
    assert message.awaited is True
    assert connection.order == ["insert", "commit", "ack"]


def test_duplicate_poison_is_dead_lettered_not_acked() -> None:
    connection = _Connection(duplicate=True)
    message = _AsyncMessage(connection.order)
    result = asyncio.run(
        settle_async_inbox_delivery(
            connection,
            _delivery(bad_hash=True, attempts=4),
            message,
        )
    )
    assert result == "NACK_DEAD_LETTER"
    assert message.awaited is True
    assert connection.order == ["insert", "commit", "nack:false"]


def test_delivery_count_header_is_prior_failures_not_attempt_number() -> None:
    assert delivery_attempt({}) == 1
    assert delivery_attempt({"x-delivery-count": 1}) == 2
    assert delivery_attempt({"x-delivery-count": 3}) == 4
    assert delivery_attempt({"x-delivery-count": "bad"}) == 1
    assert delivery_attempt({"x-delivery-count": -10}) == 1
