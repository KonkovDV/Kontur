"""Engine status reporting (donor: AeroBIM capability honesty table).

Every engine MUST report ok / skipped / failed.
Silence is never success: a missing engine appears as 'skipped'.
Any 'failed' engine that affects_verdict => kit_status = DEGRADED.
LLM/VLM are advisory_only: their failure never raises DEGRADED.

ADR-0003: LLM never writes overall_status (mirrors AeroBIM ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from kontur.domain.capabilities import AFFECTS_VERDICT, ADVISORY_ONLY, CapStatus, Capability


class EngineStatusKind(StrEnum):
    """Per-engine status visible in GET /api/v1/system/capabilities."""

    OK = "ok"
    SKIPPED = "skipped"   # optional engine not configured or not needed
    FAILED = "failed"     # engine crashed or returned error


@dataclass(frozen=True, slots=True)
class EngineReport:
    name: str
    status: EngineStatusKind
    affects_verdict: bool
    detail: str | None = None


def build_engine_report(
    capability_statuses: Mapping[str, CapStatus],
) -> tuple[EngineReport, ...]:
    """Convert raw capability statuses into typed EngineReport entries.

    Unknown capability names are mapped to SKIPPED (open-world safe).
    """
    reports: list[EngineReport] = []
    all_known = AFFECTS_VERDICT | ADVISORY_ONLY
    for name in all_known:
        cap_status = capability_statuses.get(name, CapStatus.UNAVAILABLE)
        if cap_status is CapStatus.AVAILABLE:
            kind = EngineStatusKind.OK
        elif cap_status is CapStatus.DEGRADED:
            kind = EngineStatusKind.FAILED
        else:
            # UNAVAILABLE: advisory engines are SKIPPED, verdict engines are FAILED
            if name in ADVISORY_ONLY:
                kind = EngineStatusKind.SKIPPED
            else:
                kind = EngineStatusKind.FAILED
        reports.append(
            EngineReport(
                name=name,
                status=kind,
                affects_verdict=name in AFFECTS_VERDICT,
            )
        )
    return tuple(reports)


def kit_degraded_by_engine(reports: tuple[EngineReport, ...]) -> bool:
    """True if any verdict-affecting engine is FAILED.

    Advisory (LLM) failures never trigger DEGRADED — ADR-0003.
    """
    return any(
        r.affects_verdict and r.status is EngineStatusKind.FAILED
        for r in reports
    )


def serialise_report(reports: tuple[EngineReport, ...]) -> dict[str, object]:
    """JSON-serialisable structure for GET /api/v1/system/capabilities."""
    degraded = kit_degraded_by_engine(reports)
    return {
        "overall_kit_status": "DEGRADED" if degraded else "OK",
        "engines": [
            {
                "name": r.name,
                "status": r.status.value,
                "affects_verdict": r.affects_verdict,
                "detail": r.detail,
            }
            for r in sorted(reports, key=lambda r: r.name)
        ],
    }
