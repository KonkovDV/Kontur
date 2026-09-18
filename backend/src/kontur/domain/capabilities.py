"""Матрица возможностей. Сбой advisory-слоя не валит комплект (донор AeroBIM).

OCR и разбор чертежа влияют на возможность автоматического вердикта.
LLM/VLM — sidecar: их отсутствие не превращает сверку в отказ комплекта.

Audit-2026-09: добавлены kit_degraded(), engine_health_summary(),
overall_kit_status(). Принцип AeroBIM ADR-001: silence is never success.
Каждый движок обязан быть виден в ответе /system/capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

AFFECTS_VERDICT: frozenset[str] = frozenset(
    {"vector_text", "ocr_text", "ocr_tables", "drawing_analysis"}
)
ADVISORY_ONLY: frozenset[str] = frozenset({"llm_advisory"})

# Порядок отображения в /system/capabilities (детерминированный).
KNOWN_ENGINES: tuple[str, ...] = (
    "vector_text",
    "ocr_text",
    "ocr_tables",
    "drawing_analysis",
    "llm_advisory",
)


class CapStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    status: CapStatus
    affects_verdict: bool


def describe(name: str, status: CapStatus) -> Capability:
    if name in ADVISORY_ONLY:
        return Capability(name=name, status=status, affects_verdict=False)
    if name in AFFECTS_VERDICT:
        return Capability(name=name, status=status, affects_verdict=True)
    raise ValueError(f"неизвестная возможность {name}")


def kit_blocked(capabilities: tuple[Capability, ...]) -> bool:
    """True только если недоступен слой, без которого нельзя извлечь значение.

    UNAVAILABLE verdict engine = комплект заблокирован.
    DEGRADED verdict engine = не блокирует, но виден в kit_degraded().
    Advisory UNAVAILABLE никогда не блокирует (AeroBIM ADR-003).
    """
    return any(
        item.affects_verdict and item.status is CapStatus.UNAVAILABLE for item in capabilities
    )


def kit_degraded(capabilities: tuple[Capability, ...]) -> bool:
    """True если хотя бы один verdict-affecting движок деградировал.

    Деградация не блокирует вердикт, но обязана быть видна в protocol_status
    и в /system/capabilities (AeroBIM ADR-001: silence is never success).

    Примеры деградации: OCR работает, но точность упала ниже порога;
    drawing_analysis отвечает с задержкой > p95 threshold.
    """
    return any(
        item.affects_verdict and item.status is CapStatus.DEGRADED
        for item in capabilities
    )


def engine_health_summary(capabilities: tuple[Capability, ...]) -> dict[str, str]:
    """Словарь {engine_name: status_label} для GET /api/v1/system/capabilities.

    Правила маппинга (AeroBIM ok/skipped/failed, расширено DEGRADED):
    - AVAILABLE       → 'ok'
    - DEGRADED        → 'degraded'  (нужен мониторинг, вердикт не блокирован)
    - UNAVAILABLE + affects_verdict=True  → 'failed'
    - UNAVAILABLE + affects_verdict=False → 'skipped' (advisory, ADR-003)

    Результат детерминирован: ключи отсортированы по KNOWN_ENGINES.
    """
    index: dict[str, Capability] = {cap.name: cap for cap in capabilities}
    result: dict[str, str] = {}
    for engine in KNOWN_ENGINES:
        cap = index.get(engine)
        if cap is None:
            continue
        if cap.status is CapStatus.AVAILABLE:
            result[engine] = "ok"
        elif cap.status is CapStatus.DEGRADED:
            result[engine] = "degraded"
        elif not cap.affects_verdict:
            result[engine] = "skipped"
        else:
            result[engine] = "failed"
    # Неизвестные движки добавляются в конец без гарантии порядка.
    for cap in capabilities:
        if cap.name not in result:
            if cap.status is CapStatus.AVAILABLE:
                result[cap.name] = "ok"
            elif cap.status is CapStatus.DEGRADED:
                result[cap.name] = "degraded"
            elif not cap.affects_verdict:
                result[cap.name] = "skipped"
            else:
                result[cap.name] = "failed"
    return result


def overall_kit_status(capabilities: tuple[Capability, ...]) -> str:
    """Верхнеуровневый статус комплекта для поля overall_kit_status в ответе.

    BLOCKED   — хотя бы один verdict engine UNAVAILABLE; автовердикт невозможен.
    DEGRADED  — хотя бы один verdict engine DEGRADED; автовердикт под вопросом.
    OK        — все verdict engines AVAILABLE.
    """
    if kit_blocked(capabilities):
        return "BLOCKED"
    if kit_degraded(capabilities):
        return "DEGRADED"
    return "OK"
