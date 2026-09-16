"""Внешний словарь ТЗ и внутренние типы. Заморозка контракта Gate B.

Два провода нельзя смешивать:

- процесс (п. 9.1): PENDING … COMPLETED / FINALIZED;
- протокол верификации (п. 9.3): VERIFICATION_COMPLETED / PROTOCOL_FINALIZED.

Комплектность на проводе — префикс стадии (PD_UPLOADED), внутри — UPLOADED.
AUTO_NO_DIFFERENCE существует только внутри; в протокол ТЗ и в РиН не уходит,
пока организатор не ответит на вопрос 8.
"""

from __future__ import annotations

from kontur.domain.models import DocStage
from kontur.domain.statuses import (
    WIRE_FINDING_STATUSES,
    Completeness,
    FindingStatus,
    ProcessState,
)

PROTOCOL_STATUS: dict[ProcessState, str] = {
    ProcessState.READY: "READY",
    ProcessState.VERIFYING: "VERIFYING",
    ProcessState.COMPLETED: "VERIFICATION_COMPLETED",
    ProcessState.FINALIZED: "PROTOCOL_FINALIZED",
}

TZ_UPLOAD_PREFIX: dict[DocStage, str] = {
    DocStage.PD: "PD",
    DocStage.RD: "RD",
    DocStage.ID: "ID",
}


class EmptyPackageError(ValueError):
    """Пакет без файлов — не сценарий сверки ТЗ."""


def protocol_status(process: ProcessState) -> str | None:
    """Статус протокола п. 9.3. PENDING/PARSING ещё не образуют протокол."""

    return PROTOCOL_STATUS.get(process)


def tz_upload_status(stage: DocStage, completeness: Completeness) -> str:
    """PD_UPLOADED / RD_PARTIAL / ID_MISSING — буквальные имена п. 9.1."""

    return f"{TZ_UPLOAD_PREFIX[stage]}_{completeness.value}"


def on_the_wire(status: FindingStatus) -> bool:
    """AUTO_NO_DIFFERENCE на провод ТЗ не выводится."""

    return status in WIRE_FINDING_STATUSES
