"""Redis-based finding slot for cross-restart idempotency.

Проблема: RabbitMQ доставляет at-least-once. При повторной доставке один и тот же
evidence_group_id может попасть в два разных ProcessWorkspace (после рестарта).
In-memory dedup через put_finding (по evidence_group_id) работает только внутри
одного процесса. Redis SETNX даёт cross-restart best-effort idempotency.

Принцип fail-open: если Redis недоступен — пропускаем слот и обрабатываем.
Лучше дубль находки (детектируемый), чем потеря (Stop-ship #11).

Интеграция в pipeline consumer:
    if not await claim_finding_slot(redis, finding.evidence_group_id):
        logger.info("duplicate finding skipped: %s", finding.evidence_group_id)
        return
    workspace.put_finding(finding)

Порог TTL: KONTUR_FINDING_SLOT_TTL (env, default 86400 с = 24 ч).
Префикс ключа: kontur:finding:v1:<evidence_group_id>

Refs: RT-G, ТЗ §9.1 «до двух повторов», Stop-ship #11.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

FINDING_SLOT_KEY_PREFIX = "kontur:finding:v1:"
DEFAULT_FINDING_SLOT_TTL = int(os.getenv("KONTUR_FINDING_SLOT_TTL", "86400"))


@runtime_checkable
class RedisClient(Protocol):
    """Minimal async Redis interface needed for slot operations."""

    async def set(
        self,
        name: str,
        value: Any,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        """SET key value [EX seconds] [NX]. Returns True if set, None/False if not."""
        ...


async def claim_finding_slot(
    client: RedisClient,
    evidence_group_id: str,
    ttl: int = DEFAULT_FINDING_SLOT_TTL,
) -> bool:
    """Try to claim an idempotency slot for the given finding.

    Returns True if the slot is free (caller SHOULD process the finding).
    Returns False if the slot is already taken (caller SHOULD skip -- duplicate).

    NEVER raises. Redis errors are logged as WARNING and treated as True (fail-open):
    a potential duplicate is safer than a silently dropped finding (Stop-ship #11).

    Empty/missing evidence_group_id: returns True without contacting Redis
    (no dedup key available; in-memory put_finding handles this path).

    Args:
        client: Async Redis client (e.g. redis.asyncio.Redis).
        evidence_group_id: The stable finding identity key.
        ttl: Key expiry in seconds (default: KONTUR_FINDING_SLOT_TTL env, 86400).

    Returns:
        True  -- slot is free or Redis unavailable (process the finding).
        False -- slot already claimed (skip this duplicate).
    """
    if not evidence_group_id:
        return True

    key = f"{FINDING_SLOT_KEY_PREFIX}{evidence_group_id}"
    try:
        result = await client.set(key, "1", ex=ttl, nx=True)
        return result is True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Redis finding slot unavailable for %s -- fail open (Stop-ship #11). "
            "Error: %s",
            evidence_group_id,
            exc,
        )
        return True
