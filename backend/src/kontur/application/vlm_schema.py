"""Изоляция VLM/OCR advisory: схема кандидата и детерминированный валидатор.

SOTA 2026 / OWASP LLM01–LLM09:
- VlmCandidate — строго типизированная схема (Pydantic v2):
  только advisory-поля, без write/tools/system_prompt;
- validate_vlm_candidate() — детерминированный шлюз до и после вызова VLM:
  блокирует tool-вызовы, system-prompt инъекции, утечки секретов,
  write-глаголы в тексте advisory, строки CONFIRMED_VIOLATION;
- VLM-сервис изолирован от РиН, БД протоколов и JWT-секретов;
- finding_status не меняется результатом валидатора.

Изоляция реализована на уровне схемы (нет полей → нет утечки),
не на уровне сетевых правил (это отдельный слой).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

# ── константы инъекций ──────────────────────────────────────────────────────

# Фразы, запрещённые в advisory-тексте (case-insensitive)
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (previous|all) instructions?",
        r"disregard (previous|all|your) (instructions?|rules?|constraints?)",
        r"you are now",
        r"act as (an? )?(?:different|unrestricted|jailbreak)",
        r"do not follow",
        r"override (your )?(instructions?|system|rules?)",
        r"system prompt",
        r"CONFIRMED_VIOLATION",  # автомат не пишет этот статус
        r"NEGATIVE_VERIFIED",    # только инспектор
        r"confirmed.{0,10}violation",
        r"negative.{0,10}verified",
    )
)

# write-глаголы в advisory — признак инъекции, не аналитики
_WRITE_VERB_PATTERN = re.compile(
    r"\b(update|delete|insert|drop|create|alter|execute|exec|write|commit|rollback|grant|revoke)\b",
    re.IGNORECASE,
)

# Паттерны утечки секретов (JWT, hex-secrets)
_SECRET_PATTERN = re.compile(
    r"(eyJ[A-Za-z0-9_-]{20,}|[0-9a-fA-F]{32,}|Bearer\s+\S{20,})"
)

# Максимальная длина текстовых полей
_MAX_ADVISORY_LEN = 4_000
_MAX_RAW_TOKEN_LEN = 500


# ── исключения ─────────────────────────────────────────────────────────────

class VlmIsolationError(ValueError):
    """VLM output не прошёл детерминированный шлюз изоляции."""


class VlmInjectionError(VlmIsolationError):
    """Обнаружена инъекция в тексте advisory."""


class VlmSecretLeakError(VlmIsolationError):
    """Обнаружена утечка секрета в тексте advisory."""


class VlmWriteVerbError(VlmIsolationError):
    """Запрещённый write-глагол в advisory (признак инъекции)."""


class VlmToolCallError(VlmIsolationError):
    """VLM выполнил вызов инструмента — запрещено для advisory-режима."""


# ── схема кандидата ────────────────────────────────────────────────────────

class VlmAdvisoryConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    ABSTAIN = "ABSTAIN"


class VlmCandidate(BaseModel):
    """Выход VLM в advisory-режиме.

    Поля ограничены: нет tool_calls, нет system_message, нет write-операций,
    нет полей протокола или РиН. Это advisory, не вердикт.

    finding_status не меняется на основании этой схемы — только инспектор
    присваивает CONFIRMED_VIOLATION или NEGATIVE_VERIFIED.
    """

    model_config = {"extra": "forbid", "frozen": True}

    # Что VLM «видит» на изображении (advisory)
    advisory_text: Annotated[
        str,
        Field(
            max_length=_MAX_ADVISORY_LEN,
            description="Текстовое advisory: что увидел VLM на изображении. "
                        "Не вердикт, не статус находки.",
        ),
    ]

    confidence: VlmAdvisoryConfidence = VlmAdvisoryConfidence.ABSTAIN

    # raw токен, который VLM идентифицировал (опционально)
    raw_token: Annotated[
        str | None,
        Field(
            default=None,
            max_length=_MAX_RAW_TOKEN_LEN,
            description="Токен, идентифицированный VLM на странице.",
        ),
    ] = None

    # Номер страницы (advisory, не binding)
    page_hint: Annotated[
        int | None,
        Field(default=None, ge=1, le=10_000),
    ] = None

    # Имя движка и версия (для audit)
    engine: Annotated[
        str,
        Field(max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$"),
    ]
    engine_version: Annotated[
        str,
        Field(max_length=32, pattern=r"^[a-zA-Z0-9_.+-]+$"),
    ]

    # --- запрещённые поля (нет в схеме = нет в выходе) ---
    # Нет: tool_calls, function_call, system_message, process_id,
    # jwt, secret, finding_status, CONFIRMED_VIOLATION, database_url

    @field_validator("advisory_text", mode="after")
    @classmethod
    def _no_injection_in_advisory(cls, v: str) -> str:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(v):
                raise VlmInjectionError(
                    f"advisory_text содержит запрещённый паттерн: {pattern.pattern!r}"
                )
        return v

    @field_validator("advisory_text", mode="after")
    @classmethod
    def _no_write_verbs_in_advisory(cls, v: str) -> str:
        match = _WRITE_VERB_PATTERN.search(v)
        if match:
            raise VlmWriteVerbError(
                f"advisory_text содержит write-глагол: {match.group()!r}"
            )
        return v

    @field_validator("advisory_text", mode="after")
    @classmethod
    def _no_secret_leak(cls, v: str) -> str:
        match = _SECRET_PATTERN.search(v)
        if match:
            raise VlmSecretLeakError(
                "advisory_text содержит паттерн утечки секрета"
            )
        return v


# ── публичный интерфейс ─────────────────────────────────────────────────────

def validate_vlm_candidate(
    raw: dict[str, object],
    *,
    allow_tool_calls: bool = False,
) -> VlmCandidate:
    """Детерминированный шлюз изоляции VLM (pre/post validation).

    1. Блокирует tool_calls / function_call в raw-словаре.
    2. Валидирует через VlmCandidate (Pydantic, strict).
    3. Вторичная проверка advisory_text на инъекции.

    Fail-closed: любое исключение = reject advisory, не вердикт находки.
    """
    # 1. Блокировка tool-вызовов до десериализации
    if not allow_tool_calls:
        for key in ("tool_calls", "function_call", "tools", "tool_use"):
            if key in raw:
                raise VlmToolCallError(
                    f"VLM output содержит {key!r} — tool-вызовы запрещены в advisory-режиме"
                )

    # 2. Блокировка запрещённых полей протокола
    forbidden_fields = (
        "process_id", "jwt", "secret", "token", "database_url",
        "finding_status", "confirmed_violation", "negative_verified",
    )
    lower_keys = {k.lower() for k in raw}
    for field in forbidden_fields:
        if field in lower_keys:
            raise VlmIsolationError(
                f"VLM output содержит запрещённое поле {field!r}"
            )

    # 3. Десериализация и field-level validators
    return VlmCandidate.model_validate(raw, strict=False)


def is_advisory_clean(candidate: VlmCandidate) -> bool:
    """True, если advisory прошёл все проверки изоляции.

    Использовать как последнюю линию защиты перед записью в audit.
    Не меняет finding_status.
    """
    try:
        # Повторный прогон валидаторов через model_copy
        candidate.model_copy(update={"advisory_text": candidate.advisory_text})
        return True
    except (VlmIsolationError, ValueError):
        return False
