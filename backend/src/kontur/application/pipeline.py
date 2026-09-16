"""Каскад обработки L0–L9. Порядок стадий — часть контракта, а не деталь.

Ключевое правило: предметное сравнение запускается только после успешной
проверки применимости, комплектности, актуальности и сопоставимости редакций
(ТЗ п. 9.2, шаг 3). Любая ранняя стадия может завершить разбор безопасным
статусом качества данных, и это не нарушение.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from kontur.application.intake import TZ_REJECTION_CODES
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, FindingStatus

#: Перечень ТЗ п. 9.1 живёт в `application.intake` вместе с проверками лимитов.
#: Здесь оставлен реэкспорт, чтобы список нельзя было продублировать и разойтись.
INTAKE_REJECTION_CODES: frozenset[str] = TZ_REJECTION_CODES


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

#: Стадии верификации и протокола: статус здесь присваивает инспектор
#: (ADR-0001), поэтому автоматического статуса остановки у них нет.
NON_HALTING_STAGES: frozenset[Stage] = frozenset({Stage.L8_REVIEW, Stage.L9_PROTOCOL})

#: ТЗ п. 9.2 шаг 3: сравнение только после применимости, комплектности,
#: актуальности и сопоставимости. Пропуск любой из этих стадий — не успех.
REQUIRED_PRECOMPARISON_STAGES: frozenset[Stage] = frozenset(
    {
        Stage.L1_IDENTITY,
        Stage.L2_EXTRACTION,
        Stage.L3_LOCALIZATION,
        Stage.L4_REVISION,
        Stage.L5_PAIRING,
        Stage.L6_MATRIX,
        Stage.L7_FINDINGS,
    }
)


class StageHaltError(RuntimeError):
    """У стадии нет автоматического безопасного статуса остановки."""


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: Stage
    ok: bool
    status: FindingStatus | None = None
    detail: str = ""


def halt_status(stage: Stage) -> FindingStatus:
    """Безопасный статус остановки на стадии.

    L0 не превращается в finding: вызывающий код обязан обработать reject.
    Для L8–L9 таблицы нет по существу, а не по недосмотру: находка уже
    существует, и её статус меняет только инспектор. Поднимаем явную ошибку
    вместо `KeyError`, чтобы отказ на этих стадиях нельзя было молча
    превратить в статус качества данных.
    """

    if stage is Stage.L0_INTAKE:
        raise ValueError("L0 intake failures are RejectionReason, not findings")
    if stage in NON_HALTING_STAGES:
        raise StageHaltError(
            f"{stage.name}: статус на этой стадии присваивает инспектор, "
            "автоматическая остановка не определена"
        )
    try:
        return STAGE_FAILURE_STATUS[stage]
    except KeyError as error:
        raise StageHaltError(f"{stage.name}: безопасный статус остановки не задан") from error


def run(stages: list[StageResult]) -> FindingStatus | None:
    """Первый отказ прекращает каскад и возвращает безопасный статус.

    Возврат None означает, что L1–L7 реально выполнялись и пройдены, и правило
    допущено до предметного сравнения. Пустой набор или дыра в каскаде — не
    успех: это `StageHaltError`, а не молчаливый допуск. Отказ на L8–L9 обязан
    нести явный `status`. Явный `status` не может обойти L0 и не может быть
    человеческим вердиктом (ADR-0001).
    """

    for result in sorted(stages, key=lambda item: item.stage):
        if result.ok:
            continue
        if result.stage is Stage.L0_INTAKE:
            raise ValueError("L0 intake failures are RejectionReason, not findings")
        status = result.status or halt_status(result.stage)
        if status in HUMAN_ONLY_STATUSES:
            raise StageHaltError(
                f"{result.stage.name}: {status} присваивает только инспектор, "
                "каскад не имеет права записать этот статус"
            )
        return status
    present = {result.stage for result in stages}
    missing = sorted(REQUIRED_PRECOMPARISON_STAGES - present, key=lambda item: item.value)
    if missing:
        names = ", ".join(stage.name for stage in missing)
        raise StageHaltError(
            f"пропущены стадии {names}: сравнение без L1–L7 запрещено (ТЗ п. 9.2)"
        )
    return None
