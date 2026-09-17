"""Матрица возможностей. Сбой advisory-слоя не валит комплект (донор AeroBIM).

OCR и разбор чертежа влияют на возможность автоматического вердикта.
LLM/VLM — sidecar: их отсутствие не превращает сверку в отказ комплекта.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

AFFECTS_VERDICT: frozenset[str] = frozenset(
    {"vector_text", "ocr_text", "ocr_tables", "drawing_analysis"}
)
ADVISORY_ONLY: frozenset[str] = frozenset({"llm_advisory"})


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
