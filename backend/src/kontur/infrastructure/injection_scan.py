"""Защита от prompt injection в текст, извлечённый из документов (RT-C).

Мотивация
-----------
OCR и visual layer возвращают текст из изображений. Злоумышленник
может разместить в чертеже текст «игнорируй все правила». Данный
модуль обнаруживает такие паттерны и помечает токены как
данные (data_only) — они не влияют на pipeline logic.

Oracle RT-C
-----------
«Текст «ignore rules» внутри чертежа остаётся данными
и не управляет пайплайном.»

Гарантия
---------
`scan_tokens_for_injection()` никогда не выбрасывает исключение.
Безопасный дефолт: is_clean=True (не прерываем пипелайн из-за ошибки сканера).

Ссылки
------
  docs/RED_TEAM.md — RT-C (instruction inside image)
  ADR-0001         — LLM/VLM не пишут итоговый статус
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kontur.application.extractors.number import PageToken


# ── публичные типы ────────────────────────────────────────────────────────────────


class InjectionType(str, Enum):
    """Тип обнаруженной инъекции."""

    INSTRUCTION_OVERRIDE = "INSTRUCTION_OVERRIDE"  # «ignore rules», «игнорируй правила»
    ROLE_OVERRIDE = "ROLE_OVERRIDE"               # «you are now», «ты теперь»
    PROMPT_LEAK = "PROMPT_LEAK"                   # попытка извлечь system prompt


@dataclass(frozen=True, slots=True)
class InjectionScanResult:
    """Результат сканирования токенов на инъекцию."""

    is_clean: bool
    injection_type: InjectionType | None = None
    matched_pattern: str = ""
    suspicious_tokens: tuple[str, ...] = ()
    detail: str = ""


# ── паттерны обнаружения ───────────────────────────────────────────────────────

_F = re.IGNORECASE

# Инструкция оверрайд (EN + RU)
_INSTRUCTION_OVERRIDE: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bignore\s+(all\s+)?(previous\s+)?rules?\b", _F),
    re.compile(r"\bignore\s+(all\s+)?instructions?\b", _F),
    re.compile(r"\bforget\s+(all\s+)?(previous\s+)?(rules?|instructions?)\b", _F),
    re.compile(r"\bdisregard\s+(all\s+)?rules?\b", _F),
    re.compile(r"\boverride\s+(all\s+)?rules?\b", _F),
    re.compile(r"\bnew\s+instructions?:\b", _F),
    re.compile(r"\bstop\s+following\b", _F),
    # Russian
    re.compile(r"\u0438\u0433\u043d\u043e\u0440\u0438\u0440[\u0443\u0439]+\s+\u0432\u0441\u0435\s+\u043f\u0440\u0430\u0432\u0438\u043b", _F),
    re.compile(r"\u0438\u0433\u043d\u043e\u0440\u0438\u0440[\u0443\u0439]+\s+\u043f\u0440\u0430\u0432\u0438\u043b", _F),
    re.compile(r"\u0437\u0430\u0431\u0443\u0434\u044c\s+(\u0432\u0441\u0435\s+)?\u043f\u0440\u0430\u0432\u0438\u043b", _F),
    re.compile(r"\u043e\u0442\u043c\u0435\u043d[\u0438\u044c]\s+(\u0432\u0441\u0435\s+)?\u043f\u0440\u0430\u0432\u0438\u043b", _F),
    re.compile(r"\u043d\u043e\u0432\u044b\u0435\s+\u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0438:", _F),
)

# Роль оверрайд (EN + RU)
_ROLE_OVERRIDE: tuple[re.Pattern[str], ...] = (
    re.compile(r"\byou\s+are\s+(now\s+)?a\b", _F),
    re.compile(r"\bpretend\s+(to\s+be|you\s+are)\b", _F),
    re.compile(r"\bact\s+as\s+(a|an)\b", _F),
    re.compile(r"\bfrom\s+now\s+on\s+you\s+are\b", _F),
    # Russian
    re.compile(r"\u0442\u044b\s+\u0442\u0435\u043f\u0435\u0440\u044c\b", _F),
    re.compile(r"\u043f\u0440\u0438\u0442\u0432\u043e\u0440\u0438\u0441\u044c\b", _F),
    re.compile(r"\u0441\u0434\u0435\u043b\u0430\u0439\u0441\u044f\s+(\u043a\u0430\u043a\s+)?\b", _F),
)

# Prompt leak (EN)
_PROMPT_LEAK: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bprint\s+system\s+prompt\b", _F),
    re.compile(r"\bshow\s+(me\s+)?your\s+(system\s+)?instructions\b", _F),
    re.compile(r"\brepeat\s+(everything\s+)?above\b", _F),
    re.compile(r"\bwhat\s+are\s+your\s+instructions\b", _F),
    re.compile(r"\becho\s+(back\s+)?your\s+prompt\b", _F),
)

_ALL_PATTERNS: list[tuple[re.Pattern[str], InjectionType]] = [
    *((p, InjectionType.INSTRUCTION_OVERRIDE) for p in _INSTRUCTION_OVERRIDE),
    *((p, InjectionType.ROLE_OVERRIDE) for p in _ROLE_OVERRIDE),
    *((p, InjectionType.PROMPT_LEAK) for p in _PROMPT_LEAK),
]

# Размер скользящего окна (в токенах)
_WINDOW_SIZE: int = 5


# ── публичный API ────────────────────────────────────────────────────────────────


def scan_tokens_for_injection(
    tokens: "Sequence[PageToken]",
) -> InjectionScanResult:
    """Сканировать токены на prompt injection (ТР-C).

    Использует скользящее окно _WINDOW_SIZE токенов.
    Проверяет EN и RU варианты для INSTRUCTION_OVERRIDE,
    ROLE_OVERRIDE и PROMPT_LEAK.

    Returns:
        InjectionScanResult(is_clean=True) — инъекций не обнаружено.
        InjectionScanResult(is_clean=False, ...) — обнаружена инъекция.

    Raises:
        Никогда. Безопасный дефолт: is_clean=True (пипелайн не падает).
    """
    try:
        if not tokens:
            return InjectionScanResult(is_clean=True)

        texts = [t.text for t in tokens]
        n = len(texts)

        for i in range(n):
            chunk = texts[i : i + _WINDOW_SIZE]
            joined = " ".join(chunk)
            for pattern, injection_type in _ALL_PATTERNS:
                m = pattern.search(joined)
                if m:
                    return InjectionScanResult(
                        is_clean=False,
                        injection_type=injection_type,
                        matched_pattern=pattern.pattern,
                        suspicious_tokens=tuple(chunk),
                        detail=(
                            f"Pattern {pattern.pattern!r} matched in window: {joined!r}"
                        ),
                    )

        return InjectionScanResult(is_clean=True)

    except Exception as exc:  # noqa: BLE001
        # Безопасный дефолт: не падаем пипелайн из-за ошибки сканера.
        # Дефолт is_clean=True: лучше пропустить атаку, чем уронить работу системы.
        return InjectionScanResult(
            is_clean=True,
            detail=f"Scanner error (defaulting to clean): {type(exc).__name__}: {exc}",
        )
