"""Redis-кэш паспортов по SHA-256 файла (ТЗ §9.1, RT-G).

Мотивация
---------
RabbitMQ использует at-least-once доставку: одно сообщение может быть
доставлено дважды. Без кэша одинаковый файл будет обработан дважды 
→ дублирование результата в БД.

Решение: перед обработкой проверяем Redis по SHA-256 файла.
  - Промах → обрабатываем → сохраняем в Redis.
  - Попадание → возвращаем кэшированный результат (ноль повторной работы).

Это кэш паспорта по SHA-256, не идемпотентность находки/протокола.
Oracle RT-G (ровно одна находка и одна версия протокола) этим модулем
не закрывается — см. GAP-RT-G.

Ключ: kontur:passport:v1:{sha256_hex}
   TTL: KONTUR_CACHE_TTL сек. (дефолт 3600 = 1 час)

Гарантии
--------
- `get_cached_passport()` и `set_cached_passport()` никогда не выбрасывают.
- При любой ошибке Redis пайплайн работает как без кэша (safe degradation).
- Полная сериализация: все поля включая needs_clarification, clarification_reason.
- Requires: redis[asyncio]>=5.1 (в [store] extras).

Ссылки
------
  docs/RED_TEAM.md  — RT-G (idempotency broker)
  ТЗ §9.1           — Redis cache by file hash
  ADR-0001          — LLM не определяет статус
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, Protocol

from kontur.application.passport import DocumentPassport
from kontur.domain.models import ApprovalBasis, ApprovalStatus, DocStage


class PassportCacheClient(Protocol):
    """Минимальный клиент кэша. Redis не обязателен на этапе проверки типов."""

    async def get(self, key: str) -> bytes | None: ...

    async def setex(self, key: str, time: int, value: bytes) -> object: ...


# ── конфигурация ─────────────────────────────────────────────────────────────

#: Префикс всех ключей паспорта. Изменить при смене схемы сериализации.
CACHE_KEY_PREFIX: str = "kontur:passport:v1:"

#: TTL по умолчанию. Переопределяется через KONTUR_CACHE_TTL.
DEFAULT_TTL: int = int(os.getenv("KONTUR_CACHE_TTL", "3600"))

# Обратные отображения DocStage (значения from to_schema())
_STAGE_FROM_VALUE: dict[str, DocStage] = {
    s.value: s for s in DocStage
}
_APPROVAL_FROM_VALUE: dict[str, ApprovalStatus] = {
    a.value: a for a in ApprovalStatus
}


# ── сериализация ───────────────────────────────────────────────────────────


def _passport_to_dict(passport: DocumentPassport) -> dict[str, Any]:
    """Full сериализация (все поля, вкл. needs_clarification)."""
    return {
        "file_id": passport.file_id,
        "file_hash": passport.file_hash,
        "doc_stage": passport.doc_stage.value if passport.doc_stage else None,
        "pages": passport.pages,
        "layer_kind": passport.layer_kind,
        "document_code": passport.document_code,
        "revision": passport.revision,
        "sheet": passport.sheet,
        "discipline": passport.discipline,
        "approval_status": passport.approval_status.value,
        "approval_basis": passport.approval_basis.value,
        "approval_date": (
            passport.approval_date.isoformat() if passport.approval_date else None
        ),
        "object_id": passport.object_id,
        "rotate": passport.rotate,
        "media_box": list(passport.media_box) if passport.media_box else None,
        "crop_box": list(passport.crop_box) if passport.crop_box else None,
        "has_embedded_text": passport.has_embedded_text,
        "text_render_agreement": passport.text_render_agreement,
        "extraction_confidence": passport.extraction_confidence,
        "needs_clarification": passport.needs_clarification,
        "clarification_reason": passport.clarification_reason,
    }


def _passport_from_dict(d: dict[str, Any]) -> DocumentPassport:
    """Deserialize DocumentPassport из dict. Выбрасывает при невалидном формате."""
    stage_str: str | None = d.get("doc_stage")
    stage = _STAGE_FROM_VALUE.get(stage_str) if stage_str else None

    approval_str: str | None = d.get("approval_status", "UNKNOWN")
    approval = _APPROVAL_FROM_VALUE.get(
        approval_str or "UNKNOWN", ApprovalStatus.UNKNOWN
    )
    basis = ApprovalBasis(str(d.get("approval_basis") or ApprovalBasis.UNPROVEN.value))

    approval_date_str: str | None = d.get("approval_date")
    approval_date: date | None = (
        date.fromisoformat(approval_date_str) if approval_date_str else None
    )

    media_raw: list[float] | None = d.get("media_box")
    media_box: tuple[float, ...] | None = (
        tuple(float(x) for x in media_raw) if media_raw else None
    )
    crop_raw: list[float] | None = d.get("crop_box")
    crop_box: tuple[float, ...] | None = (
        tuple(float(x) for x in crop_raw) if crop_raw else None
    )

    return DocumentPassport(
        file_id=str(d["file_id"]),
        file_hash=str(d["file_hash"]),
        doc_stage=stage,
        pages=int(d.get("pages", 1)),
        layer_kind=str(d.get("layer_kind", "vector")),
        document_code=d.get("document_code") or None,
        revision=d.get("revision") or None,
        sheet=d.get("sheet") or None,
        discipline=d.get("discipline") or None,
        approval_status=approval,
        approval_basis=basis,
        approval_date=approval_date,
        object_id=d.get("object_id") or None,
        rotate=int(d.get("rotate", 0)),
        media_box=media_box,
        crop_box=crop_box,
        has_embedded_text=bool(d.get("has_embedded_text", False)),
        text_render_agreement=d.get("text_render_agreement"),
        extraction_confidence=d.get("extraction_confidence"),
        needs_clarification=bool(d.get("needs_clarification", False)),
        clarification_reason=d.get("clarification_reason") or None,
    )


def passport_to_bytes(passport: DocumentPassport) -> bytes:
    """JSON-сериализация паспорта для хранения в Redis."""
    return json.dumps(_passport_to_dict(passport), ensure_ascii=False).encode("utf-8")


def passport_from_bytes(data: bytes) -> DocumentPassport:
    """Deserialize паспорт из JSON-байт Redis."""
    return _passport_from_dict(json.loads(data))


# ── асинхронные API ─────────────────────────────────────────────────────────


async def get_cached_passport(
    client: PassportCacheClient,
    file_hash: str,
) -> DocumentPassport | None:
    """Получить паспорт из кэша. None если не найден или ошибка Redis.

    Никогда не выбрасывает. При ошибке Redis — safe degradation: пайплайн
    обрабатывает файл заново.
    """
    try:
        key = f"{CACHE_KEY_PREFIX}{file_hash}"
        data: bytes | None = await client.get(key)
        if data is None:
            return None
        return passport_from_bytes(data)
    except Exception:  # noqa: BLE001
        return None


async def set_cached_passport(
    client: PassportCacheClient,
    file_hash: str,
    passport: DocumentPassport,
    ttl: int = DEFAULT_TTL,
) -> None:
    """Сохранить паспорт в кэш. Игнорировать ошибки Redis.

    Никогда не выбрасывает. При ошибке Redis — safe degradation:
    следующий дубликат тоже будет обработан (но не создаст новый результат).
    """
    try:
        key = f"{CACHE_KEY_PREFIX}{file_hash}"
        data = passport_to_bytes(passport)
        await client.setex(key, ttl, data)
    except Exception:  # noqa: BLE001
        return
