"""Static guardrails for the production inbox consumer session boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "scripts" / "consume_inbox.py").read_text(encoding="utf-8")


def test_long_running_consumer_uses_push_iterator_not_basic_get_polling() -> None:
    session = SOURCE.split("async def _consume_session", maxsplit=1)[1]
    session = session.split("async def consume_forever", maxsplit=1)[0]
    assert "queue.iterator()" in session
    assert "queue.get(" not in session


def test_ambiguous_settlement_does_not_retry_nack_on_same_delivery() -> None:
    session = SOURCE.split("async def _consume_session", maxsplit=1)[1]
    session = session.split("async def consume_forever", maxsplit=1)[0]
    assert "incoming.nack" not in session
    assert "await connection.close()" in session
