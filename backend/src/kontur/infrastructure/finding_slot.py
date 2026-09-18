"""Redis idempotency slot для находок (RT-G, ТЗ §9.1).

Мотивация
---------
RabbitMQ at-least-once delivery: одно сообщение может быть доставлено дважды.
Без защиты put_finding() с одинаковым evidence_group_id будет вызван дважды
в двух разных ProcessWorkspace → дубли результата в БД.

Решение: перед записью находки проверяем Redis через SETNX.
  - Промах (ключа нет) → SETNX устанавливает ключ → обрабатываем.
  - Попадание (ключ уже есть) → находка уже обработана → пропускаем (False).
  - Ошибка Redis → FAIL OPEN: возвращаем True + предупреждение в лог.
    Дубль лучше потери. In-memory dedup в put_finding снижает риск при рестарте
    в том же процессе; cross-restart защита — только best-effort.

Ключ: kontur:finding:v1:{evidence_group_id}
  TTL: KONTUR_FINDING_SLOT_TTL сек. (default 86400 = 24 часа)

Гарантии
--------
- claim_finding_slot() никогда не выбрасывает.
- При любой ошибке Redis → True (fail open), warning в лог.
- Пустой evidence_group_id → True (fail open), warning в лог, Redis не вызывается.

Интеграция
----------
Вызвать ДО put_finding() в pipeline consumer:

    if not await claim_finding_slot(redis, finding.evidence_group_id):
        logger.info("duplicate finding skipped: %s", finding.evidence_group_id)
        return
    workspace.put_finding(finding)

Ссылки
------
  docs/RED_TEAM.md  — RT-G (idempotency broker)
  ТЗ §9.1           — Redis cache by file hash
  infrastructure/cache.py — passport cache (образец safe degradation)
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

logger = logging.getLogger(__name__)

#: Префикс всех ключей finding-slot. Изменить при смене схемы.
FINDING_SLOT_KEY_PREFIX: str = "kontur:finding:v1:"

#: TTL по умолчанию. Переопределяется через KONTUR_FINDING_SLOT_TTL.
DEFAULT_FINDING_SLOT_TTL: int = int(
    os.getenv("KONTUR_FINDING_SLOT_TTL", "86400")
)


class FindingSlotClient(Protocol):
    """Минимальный Redis-совместимый клиент для finding slot.

    Совместим с redis.asyncio.Redis (метод set с параметрами nx=True, ex=int).
    Redis не является обязательной зависимостью для прохождения типов.
    """

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        nx: bool,
        ex: int,
    ) -> bool | None:
        """SETNX-like: вернуть True/1 если ключ установлен, None/False если уже существует."""
        ...


async def claim_finding_slot(
    client: FindingSlotClient,
    evidence_group_id: str,
    ttl: int = DEFAULT_FINDING_SLOT_TTL,
) -> bool:
    """Попытаться занять слот для находки через Redis SETNX.

    Returns
    -------
    True  — слот свободен и занят нами (обрабатывать находку), или Redis
            недоступен (fail open: лучше дубль, чем потеря).
    False — слот уже занят (дублирующая доставка, пропустить находку).

    Никогда не выбрасывает. При любой ошибке Redis — fail open + warn log.

    Parameters
    ----------
    client:
        Redis-совместимый async клиент (FindingSlotClient).
    evidence_group_id:
        Детерминированный ключ находки (SHA-256 или comparison_key()).
        Пустая строка → fail open, Redis не вызывается.
    ttl:
        TTL слота в секундах (default KONTUR_FINDING_SLOT_TTL = 86400).
    """
    if not evidence_group_id or not evidence_group_id.strip():
        logger.warning(
            "claim_finding_slot: пустой evidence_group_id — fail open "
            "(Redis не вызывается)"
        )
        return True

    try:
        key = f"{FINDING_SLOT_KEY_PREFIX}{evidence_group_id}"
        result = await client.set(key, b"1", nx=True, ex=ttl)
        # redis.asyncio: SETNX success → True; key already exists → None.
        if result:
            return True
        logger.debug("finding slot уже занят: %s", evidence_group_id)
        return False
    except Exception:  # noqa: BLE001
        logger.warning(
            "claim_finding_slot: Redis недоступен для %s — fail open",
            evidence_group_id,
        )
        return True
