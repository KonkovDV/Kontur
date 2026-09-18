"""Тесты FindingSlotCache (RT-G, stop-ship #11, safe degradation).

Проверяем три пути:
  1. Новый слот → True (обработать).
  2. Слот уже занят → False (дубль, пропустить).
  3. Redis недоступен → True (fail open, НЕ отбрасывать находку).
  4. Пустой evidence_group_id → True (fail open), Redis не вызывается.
"""
from __future__ import annotations

import pytest

from kontur.infrastructure.finding_slot import (
    FINDING_SLOT_KEY_PREFIX,
    claim_finding_slot,
)


class _OkClient:
    """Redis mock: SETNX всегда успешен (новый ключ)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def set(self, key: str, value: bytes, *, nx: bool, ex: int) -> bool | None:
        self.calls.append(key)
        return True  # SETNX success


class _DuplicateClient:
    """Redis mock: ключ уже существует (дублирующая доставка)."""

    async def set(self, key: str, value: bytes, *, nx: bool, ex: int) -> bool | None:
        return None  # SETNX failed — key already present


class _ErrorClient:
    """Redis mock: выбрасывает исключение при любом вызове."""

    async def set(self, key: str, value: bytes, *, nx: bool, ex: int) -> bool | None:
        raise ConnectionError("Redis down")


@pytest.mark.asyncio
async def test_new_slot_returns_true() -> None:
    """Первый вызов: слот свободен → разрешить обработку."""
    client = _OkClient()
    result = await claim_finding_slot(client, "egrp-abc123")
    assert result is True
    assert len(client.calls) == 1
    assert client.calls[0] == f"{FINDING_SLOT_KEY_PREFIX}egrp-abc123"


@pytest.mark.asyncio
async def test_duplicate_slot_returns_false() -> None:
    """Повторная доставка: ключ уже есть → пропустить (дубль)."""
    result = await claim_finding_slot(_DuplicateClient(), "egrp-abc123")
    assert result is False


@pytest.mark.asyncio
async def test_redis_error_fails_open() -> None:
    """Stop-ship #11: ошибка Redis НЕ должна отбрасывать находку.

    PR #22 был отклонён именно потому, что drop на ошибке Redis нарушал
    это требование. Правильное поведение: fail open (True).
    """
    result = await claim_finding_slot(_ErrorClient(), "egrp-abc123")
    assert result is True, (
        "fail open: Redis недоступен не должен приводить к потере находки"
    )


@pytest.mark.asyncio
async def test_empty_evidence_group_id_fails_open_without_redis_call() -> None:
    """Пустой ключ: fail open, Redis не вызывается (нет смысла занимать '')."""
    client = _OkClient()
    result = await claim_finding_slot(client, "  ")
    assert result is True
    assert client.calls == [], "Redis не должен вызываться при пустом ключе"


@pytest.mark.asyncio
async def test_ttl_passed_to_redis() -> None:
    """TTL пробрасывается в Redis.set(ex=...)."""

    class _CapturingClient:
        ttl_received: int = 0

        async def set(self, key: str, value: bytes, *, nx: bool, ex: int) -> bool | None:
            _CapturingClient.ttl_received = ex
            return True

    await claim_finding_slot(_CapturingClient(), "egrp-xyz", ttl=7200)
    assert _CapturingClient.ttl_received == 7200
