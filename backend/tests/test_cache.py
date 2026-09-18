"""Тесты Redis-кэша паспортов (GAP-REDIS, RT-G).

Используем asyncio.run() — не требует pytest-asyncio.
Redis-клиент мокается через unittest.mock.AsyncMock.
"""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

from kontur.application.passport import DocumentPassport
from kontur.domain.models import ApprovalStatus, DocStage
from kontur.infrastructure.cache import (
    CACHE_KEY_PREFIX,
    get_cached_passport,
    passport_from_bytes,
    passport_to_bytes,
    set_cached_passport,
)

# ── фабрики ─────────────────────────────────────────────────────────────

_HASH = "a" * 64


def _passport(
    file_id: str = "doc-001",
    file_hash: str = _HASH,
    doc_stage: DocStage | None = DocStage.PD,
    document_code: str | None = "ABC-001",
    needs_clarification: bool = False,
    clarification_reason: str | None = None,
    approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    approval_date: date | None = None,
    extraction_confidence: float | None = None,
) -> DocumentPassport:
    return DocumentPassport(
        file_id=file_id,
        file_hash=file_hash,
        doc_stage=doc_stage,
        pages=2,
        layer_kind="vector",
        document_code=document_code,
        revision="1",
        approval_status=approval_status,
        approval_date=approval_date,
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
        extraction_confidence=extraction_confidence,
    )


def _mock_client(stored: dict[str, bytes] | None = None) -> AsyncMock:
    """AsyncMock Redis-клиент с dict-бэкендом."""
    data: dict[str, bytes] = stored if stored is not None else {}
    client = AsyncMock()

    async def fake_get(key: str) -> bytes | None:
        return data.get(key)

    async def fake_setex(key: str, ttl: int, value: bytes) -> None:
        data[key] = value

    client.get.side_effect = fake_get
    client.setex.side_effect = fake_setex
    return client


# ── passport_to_bytes / passport_from_bytes ───────────────────────────────────


def test_serialization_round_trip_basic() -> None:
    """JSON round-trip сохраняет все поля."""
    p = _passport()
    result = passport_from_bytes(passport_to_bytes(p))
    assert result.file_id == p.file_id
    assert result.file_hash == p.file_hash
    assert result.doc_stage is DocStage.PD
    assert result.document_code == p.document_code
    assert result.approval_status is ApprovalStatus.APPROVED


def test_serialization_needs_clarification() -> None:
    """`needs_clarification=True` сохраняется и восстанавливается."""
    p = _passport(
        needs_clarification=True,
        clarification_reason="шифр не найден",
    )
    result = passport_from_bytes(passport_to_bytes(p))
    assert result.needs_clarification is True
    assert result.clarification_reason == "шифр не найден"


@pytest.mark.parametrize("stage", [DocStage.PD, DocStage.RD, DocStage.ID, None])
def test_serialization_all_stages(stage: DocStage | None) -> None:
    """Все значения DocStage работают round-trip."""
    p = _passport(doc_stage=stage)
    result = passport_from_bytes(passport_to_bytes(p))
    assert result.doc_stage is stage


def test_serialization_approval_date() -> None:
    """approval_date ISO round-trip."""
    p = _passport(approval_date=date(2025, 6, 15))
    result = passport_from_bytes(passport_to_bytes(p))
    assert result.approval_date == date(2025, 6, 15)


def test_serialization_extraction_confidence_none() -> None:
    """extraction_confidence=None round-trip."""
    p = _passport(extraction_confidence=None)
    result = passport_from_bytes(passport_to_bytes(p))
    assert result.extraction_confidence is None


def test_serialization_extraction_confidence_value() -> None:
    """extraction_confidence=0.75 round-trip."""
    p = _passport(extraction_confidence=0.75)
    result = passport_from_bytes(passport_to_bytes(p))
    assert result.extraction_confidence == pytest.approx(0.75)


# ── get_cached_passport / set_cached_passport ──────────────────────────────


def test_cache_miss_returns_none() -> None:
    """Промах кэша → None."""

    async def run() -> None:
        client = _mock_client()
        result = await get_cached_passport(client, _HASH)
        assert result is None

    asyncio.run(run())


def test_cache_hit_returns_passport() -> None:
    """Попадание кэша → паспорт round-trip."""

    async def run() -> None:
        p = _passport()
        stored = {f"{CACHE_KEY_PREFIX}{_HASH}": passport_to_bytes(p)}
        client = _mock_client(stored)
        result = await get_cached_passport(client, _HASH)
        assert result is not None
        assert result.file_id == p.file_id
        assert result.document_code == p.document_code

    asyncio.run(run())


def test_set_then_get_round_trip() -> None:
    """Полный цикл: set → get → passport."""

    async def run() -> None:
        p = _passport(needs_clarification=True, clarification_reason="test")
        client = _mock_client()
        await set_cached_passport(client, _HASH, p)
        result = await get_cached_passport(client, _HASH)
        assert result is not None
        assert result.needs_clarification is True
        assert result.clarification_reason == "test"

    asyncio.run(run())


def test_get_never_raises_on_redis_error() -> None:
    """Ошибка Redis на get → None (не выбрасывает)."""

    async def run() -> None:
        client = AsyncMock()
        client.get.side_effect = ConnectionError("Redis timeout")
        result = await get_cached_passport(client, _HASH)
        assert result is None

    asyncio.run(run())


def test_set_never_raises_on_redis_error() -> None:
    """Ошибка Redis на set → ничего (не выбрасывает)."""

    async def run() -> None:
        client = AsyncMock()
        client.setex.side_effect = ConnectionError("Redis timeout")
        await set_cached_passport(client, _HASH, _passport())  # не должно пасть

    asyncio.run(run())


def test_set_uses_correct_ttl() -> None:
    """setex вызывается с переданным TTL."""

    async def run() -> None:
        client = AsyncMock()
        client.setex.return_value = True
        await set_cached_passport(client, _HASH, _passport(), ttl=1800)
        call_args = client.setex.call_args
        # аргумент TTL (2й positional или keyword)
        if call_args.args:
            assert call_args.args[1] == 1800
        else:
            assert call_args.kwargs.get("time") == 1800

    asyncio.run(run())


def test_key_has_correct_prefix() -> None:
    """Redis-ключ содержит префикс kontur:passport:v1:."""

    async def run() -> None:
        client = AsyncMock()
        client.setex.return_value = True
        file_hash = "b" * 64
        await set_cached_passport(client, file_hash, _passport(file_hash=file_hash))
        call_args = client.setex.call_args
        key = call_args.args[0] if call_args.args else call_args.kwargs.get("name", "")
        assert str(key) == f"{CACHE_KEY_PREFIX}{file_hash}"

    asyncio.run(run())


# ── RT-G: idempotency oracle ──────────────────────────────────────────────────


def test_rt_g_duplicate_message_returns_same_result() -> None:
    """Дубликат at-least-once → один результат без повторной обработки.

    Сценарий RT-G:
      1. Первое сообщение (hash=H): кэш пуст → обрабатываем → сохраняем в Redis.
      2. Дубликат (hash=H): кэш есть → возвращаем тот же результат без повторного анализа.
      3. document_code, needs_clarification совпадают — один бизнес-эффект.
    """

    async def run() -> None:
        passport = _passport(
            file_id="doc-dup-001",
            document_code="XYZ-999",
        )
        client = _mock_client()  # пустой dict-бэкенд

        # Шаг 1: первое сообщение
        hit1 = await get_cached_passport(client, passport.file_hash)
        assert hit1 is None, "Свежий кэш должен дать промах"

        # Пипелайн обрабатывает файл и сохраняет в кэш
        await set_cached_passport(client, passport.file_hash, passport)

        # Шаг 2: дубликат — кэш уже есть
        hit2 = await get_cached_passport(client, passport.file_hash)
        assert hit2 is not None, "Дубликат должен вернуть паспорт из кэша"

        # Oracle RT-G: один бизнес-эффект
        assert hit2.document_code == passport.document_code
        assert hit2.file_id == passport.file_id
        assert hit2.doc_stage is passport.doc_stage

        # Гарантия: setex вызван ровно один раз (не дублировался)
        assert client.setex.call_count == 1, (
            f"Ожидали 1 вызов setex, получено: {client.setex.call_count}"
        )

    asyncio.run(run())
