"""Идемпотентное хранение находок (RT-G, ТЗ §9.1).

At-least-once доставка очереди может повторить одно и то же сообщение.
Пайплайн обязан гарантировать ровно один бизнес-эффект для каждой
уникальной тройки (object_id, rule_code, file_ids).

Реализация
----------
Перед записью находки выполняем Redis SET NX (Set if Not eXists).
Если ключ уже существует — дубль пропускаем.
Ключ = comparison_key(object_id, rule_code, file_ids).

Ключ: kontur:finding:v1:{comparison_key}
TTL:  KONTUR_FINDING_TTL сек. (дефолт 86400 = 24 ч)

Гарантии
--------
- `claim_finding_slot()` никогда не выбрасывает.
- При ошибке Redis — возвращает False (safe degradation): пайплайн не падает,
  находка может быть пропущена. Это безопаснее дублирования протокола.
- Требует Redis >= 6 (SET NX EX — одна атомарная команда).

Ссылки
------
  docs/RED_TEAM.md      — RT-G oracle (at-least-once → exactly-once)
  domain/idempotency.py — comparison_key
  ТЗ §9.1               — at-least-once → exactly-once бизнес-эффект
"""
from __future__ import annotations

import os
from typing import Protocol

from kontur.domain.idempotency import comparison_key as _make_key

#: Префикс ключей идемпотентности находок. Изменить при смене схемы.
FINDING_KEY_PREFIX: str = "kontur:finding:v1:"

#: TTL по умолчанию. Переопределяется через KONTUR_FINDING_TTL.
DEFAULT_FINDING_TTL: int = int(os.getenv("KONTUR_FINDING_TTL", "86400"))


class FindingCacheClient(Protocol):
    """Минимальный интерфейс Redis-клиента для идемпотентности находок.

    Реальный `redis.asyncio.Redis` соответствует этому протоколу.
    Используем Protocol, чтобы не зависеть от redis-py на уровне доменных типов.
    """

    async def set(
        self,
        key: str,
        value: bytes,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool | None:
        """SET [NX] [EX seconds].

        Returns
        -------
        True  — ключ создан.
        None  — NX=True и ключ уже существует.
        """
        ...


async def claim_finding_slot(
    client: FindingCacheClient,
    object_id: str,
    rule_code: str,
    file_ids: tuple[str, ...],
    ttl: int = DEFAULT_FINDING_TTL,
) -> bool:
    """Зарезервировать слот для находки.

    Returns True при первом вызове для данной тройки (object_id, rule_code,
    file_ids); False если слот уже занят или Redis недоступен.

    Атомарный SETNX обеспечивает: ровно один вызов вернёт True в течение TTL.

    Parameters
    ----------
    client:    Асинхронный Redis-клиент.
    object_id: Идентификатор объекта КС.
    rule_code: Код правила (PZ-001, AR-041, …).
    file_ids:  Хеши файлов-эталонов упорядоченным кортежем.
    ttl:       Время жизни ключа (секунды).

    Returns
    -------
    True  — слот свободен; пайплайн ДОЛЖЕН создать находку.
    False — дубль или ошибка Redis; находку НАДО пропустить.
    """
    try:
        key = f"{FINDING_KEY_PREFIX}{_make_key(object_id, rule_code, file_ids)}"
        result = await client.set(key, b"1", nx=True, ex=ttl)
        # Redis: True = SET выполнен (ключ создан), None = NX-провал (ключ был)
        return result is True
    except Exception:  # noqa: BLE001
        # safe degradation: при недоступности Redis не блокируем пайплайн
        return False
