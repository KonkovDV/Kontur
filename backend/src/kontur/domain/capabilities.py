"""Матрица возможностей. Сбой advisory-слоя не валит комплект (донор AeroBIM).

Gate I (24.09): ocr_text = AVAILABLE если Tesseract-5 установлен,
иначе UNAVAILABLE (штатное поведение до Gate I).
ОСТАЛЬНОЕ БЕЗ ИЗМЕНЕНИЙ.
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


def _ocr_text_status() -> CapStatus:
    """Gate I: AVAILABLE если Tesseract-5 установлен, иначе UNAVAILABLE."""
    try:
        from kontur.infrastructure.ocr_verifier import tesseract_available  # noqa: PLC0415
        return CapStatus.AVAILABLE if tesseract_available() else CapStatus.UNAVAILABLE
    except ImportError:
        return CapStatus.UNAVAILABLE


def live_kit() -> tuple[Capability, ...]:
    """Слои, которые сейчас реально стоят на пути извлечения значения."""
    caps: list[Capability] = [describe("vector_text", CapStatus.AVAILABLE)]
    if _ocr_text_status() is CapStatus.AVAILABLE:
        caps.append(describe("ocr_text", CapStatus.AVAILABLE))
    return tuple(caps)


def declared_capabilities() -> tuple[Capability, ...]:
    """Честный снимок: вектор жив; OCR — по наличию Tesseract; остальное не стоит."""
    return (
        describe("vector_text", CapStatus.AVAILABLE),
        describe("ocr_text", _ocr_text_status()),
        describe("ocr_tables", CapStatus.UNAVAILABLE),
        describe("drawing_analysis", CapStatus.UNAVAILABLE),
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
            "overall считается по живому пути. "
            "ocr_text=AVAILABLE при наличии Tesseract-5 (Gate I). "
            "UNAVAILABLE у OCR/чертежа — явный пробел, не тихий успех."
        ),
    }
