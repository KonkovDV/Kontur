"""Каскад обработки L0–L9. Порядок стадий — часть контракта, а не деталь.

Ключевое правило: предметное сравнение запускается только после успешной
проверки применимости, комплектности, актуальности и сопоставимости редакций
(ТЗ п. 9.2, шаг 3). Любая ранняя стадия может завершить разбор безопасным
статусом качества данных, и это не нарушение.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from kontur.domain.statuses import FindingStatus

INTAKE_REJECTION_CODES = frozenset(
    {
        "UNSUPPORTED_FORMAT",
        "CORRUPTED_FILE",
        "FILE_TOO_LARGE",
        "BATCH_LIMIT_EXCEEDED",
        "ANTIVIRUS_REJECTED",
        "ENCRYPTED_FILE",
        "PROCESSING_TIMEOUT",
    }
)


class Stage(IntEnum):
    L0_INTAKE = 0
    L1_IDENTITY = 1
    L2_EXTRACTION = 2
    L3_LOCALIZATION = 3
    L4_REVISION = 4
    L5_PAIRING = 5
    L6_MATRIX = 6
    L7_FINDINGS = 7
    L8_REVIEW = 8
    L9_PROTOCOL = 9


#: Отказ стадии → статус качества данных, не нарушение.
#: L0 не входит: сбой загрузки — RejectionReason, а не finding.
STAGE_FAILURE_STATUS: dict[Stage, FindingStatus] = {
    Stage.L1_IDENTITY: FindingStatus.CLARIFICATION_REQUIRED,
    Stage.L2_EXTRACTION: FindingStatus.LOW_QUALITY,
    Stage.L3_LOCALIZATION: FindingStatus.LOW_QUALITY,
    Stage.L4_REVISION: FindingStatus.CLARIFICATION_REQUIRED,
    Stage.L5_PAIRING: FindingStatus.NOT_COMPARABLE,
    Stage.L6_MATRIX: FindingStatus.CLARIFICATION_REQUIRED,
    Stage.L7_FINDINGS: FindingStatus.ABSTAIN,
}


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: Stage
    ok: bool
    status: FindingStatus | None = None
    detail: str = ""


def halt_status(stage: Stage) -> FindingStatus:
    """Безопасный статус остановки на стадии.

    L0 не превращается в finding: вызывающий код обязан обработать reject.
    """

    if stage is Stage.L0_INTAKE:
        raise ValueError("L0 intake failures are RejectionReason, not findings")
    return STAGE_FAILURE_STATUS[stage]


def run(stages: list[StageResult]) -> FindingStatus | None:
    """Первый отказ прекращает каскад и возвращает безопасный статус.

    Возврат None означает, что все предварительные стадии пройдены и правило
    допущено до предметного сравнения.
    """

    for result in sorted(stages, key=lambda item: item.stage):
        if not result.ok:
            return result.status or halt_status(result.stage)
    return None
