"""Tests for Redis finding slot idempotency (Stop-ship #11)."""
from __future__ import annotations

from typing import Any

import pytest

from kontur.infrastructure.finding_slot import (
    DEFAULT_FINDING_SLOT_TTL,
    FINDING_SLOT_KEY_PREFIX,
    claim_finding_slot,
)


class _MockRedis:
    """In-memory Redis mock implementing the minimal RedisClient Protocol."""

    def __init__(self, *, fail: bool = False) -> None:
        self._store: dict[str, str] = {}
        self._fail = fail
        self.calls: list[dict[str, Any]] = []

    async def set(
        self,
        name: str,
        value: Any,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        self.calls.append({"name": name, "value": value, "ex": ex, "nx": nx})
        if self._fail:
            raise ConnectionError("Redis connection refused")
        if nx and name in self._store:
            return None
        self._store[name] = str(value)
        return True


@pytest.mark.asyncio
async def test_new_slot_returns_true() -> None:
    redis = _MockRedis()
    result = await claim_finding_slot(redis, "eg-abc-001")
    assert result is True


@pytest.mark.asyncio
async def test_existing_slot_returns_false() -> None:
    redis = _MockRedis()
    first = await claim_finding_slot(redis, "eg-abc-002")
    second = await claim_finding_slot(redis, "eg-abc-002")
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_redis_error_fails_open() -> None:
    """Stop-ship #11: Redis error MUST return True (fail open), never drop the finding."""
    redis = _MockRedis(fail=True)
    result = await claim_finding_slot(redis, "eg-abc-003")
    assert result is True, (
        "Stop-ship #11 violated: Redis error must fail open, not drop the finding"
    )


@pytest.mark.asyncio
async def test_empty_evidence_group_id_no_redis_call() -> None:
    redis = _MockRedis()
    result = await claim_finding_slot(redis, "")
    assert result is True
    assert redis.calls == []


@pytest.mark.asyncio
async def test_ttl_passed_to_redis() -> None:
    redis = _MockRedis()
    await claim_finding_slot(redis, "eg-abc-004", ttl=3600)
    assert redis.calls[0]["ex"] == 3600


@pytest.mark.asyncio
async def test_default_ttl_is_env_configured() -> None:
    redis = _MockRedis()
    await claim_finding_slot(redis, "eg-abc-005")
    assert redis.calls[0]["ex"] == DEFAULT_FINDING_SLOT_TTL


@pytest.mark.asyncio
async def test_key_prefix_is_versioned() -> None:
    redis = _MockRedis()
    await claim_finding_slot(redis, "eg-abc-006")
    assert redis.calls[0]["name"].startswith(FINDING_SLOT_KEY_PREFIX)
    assert "eg-abc-006" in redis.calls[0]["name"]
