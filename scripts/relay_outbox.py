"""Relay PENDING outbox rows to RabbitMQ with publisher confirms.

Broker confirm is not Rin ACK and not exactly-once. Inbox/dedup is a later slice.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import psycopg

from kontur.infrastructure.outbox import AmqpConfirmedPublisher, relay_once_postgres


def main() -> int:
    dsn = os.environ.get("KONTUR_DB_URL")
    amqp = os.environ.get("KONTUR_AMQP_URL")
    if not dsn or not amqp:
        print("KONTUR_DB_URL and KONTUR_AMQP_URL are required; not claiming Rin", file=sys.stderr)
        return 2
    publisher = AmqpConfirmedPublisher(amqp)
    with psycopg.connect(dsn) as connection:
        connection.execute("BEGIN")
        try:
            result = relay_once_postgres(connection, publisher, datetime.now(tz=UTC))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    if result is None:
        print("outbox empty")
        return 0
    print(result)
    return 0 if result == "DELIVERED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
