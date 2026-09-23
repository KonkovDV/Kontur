"""Матрица возможностей. Сбой advisory-слоя не валит комплект (донор AeroBIM).

OCR и разбор чертежа влияют на возможность автоматического вердикта.
LLM/VLM — sidecar: их отсутствие не превращает сверку в отказ комплекта.
Тишина не считается успехом: отсутствующий слой объявляется явно.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

AFFECTS_VERDICT: frozenset[str] = frozenset(
    {"vector_text", "ocr_text", "ocr_tables", "drawing_analysis"}
)
ADVISORY_ONLY: frozenset[str] = frozenset({"llm_advisory"})

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
    """True только если недоступен слой, без которого нельзя извлечь значение."""

    return any(
        item.affects_verdict and item.status is CapStatus.UNAVAILABLE for item in capabilities
    )


def kit_degraded(capabilities: tuple[Capability, ...]) -> bool:
    """True если вердиктный слой жив, но не в полном качестве."""

    return any(item.affects_verdict and item.status is CapStatus.DEGRADED for item in capabilities)


def overall_kit_status(capabilities: tuple[Capability, ...]) -> CapStatus:
    if kit_blocked(capabilities):
        return CapStatus.UNAVAILABLE
    if kit_degraded(capabilities):
        return CapStatus.DEGRADED
    return CapStatus.AVAILABLE


def engine_health_summary(capabilities: tuple[Capability, ...]) -> dict[str, list[str]]:
    """Разложить известные движки. Непереданные имена — skipped, не healthy."""

    by_name = {item.name: item for item in capabilities}
    healthy: list[str] = []
    degraded: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []
    for name in KNOWN_ENGINES:
        item = by_name.get(name)
        if item is None:
            skipped.append(name)
            continue
        if item.status is CapStatus.AVAILABLE:
            healthy.append(name)
        elif item.status is CapStatus.DEGRADED:
            degraded.append(name)
        elif item.affects_verdict:
            failed.append(name)
        else:
            skipped.append(name)
    return {
        "healthy": healthy,
        "degraded": degraded,
        "failed": failed,
        "skipped": skipped,
    }


def live_kit() -> tuple[Capability, ...]:
    """Слои, которые сейчас реально стоят на пути извлечения значения."""

    return (describe("vector_text", CapStatus.AVAILABLE),)


def declared_capabilities() -> tuple[Capability, ...]:
    """Векторный текст жив. Штрихи листа читаются, но не измеряют сечение.
    OCR и LLM в запросе не стоят."""

    return (
        describe("vector_text", CapStatus.AVAILABLE),
        describe("ocr_text", CapStatus.UNAVAILABLE),
        describe("ocr_tables", CapStatus.UNAVAILABLE),
        describe("drawing_analysis", CapStatus.DEGRADED),
        describe("llm_advisory", CapStatus.UNAVAILABLE),
    )


def capabilities_payload() -> dict[str, object]:
    declared = declared_capabilities()
    live = live_kit()
    return {
        "overall": overall_kit_status(live).value,
        "kit_blocked": kit_blocked(live),
        "engines": [
            {
                "name": item.name,
                "status": item.status.value,
                "affects_verdict": item.affects_verdict,
            }
            for item in declared
        ],
        "health": engine_health_summary(declared),
        "note": (
            "overall считается по живому пути (векторный текст). "
            "OCR остаётся UNAVAILABLE. drawing_analysis DEGRADED: "
            "сетка штрихов листа читается и не закрывает гейт I."
        ),
    }
