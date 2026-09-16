"""Перечисления статусов. Пять независимых доменов (ADR-0005).

Смешение доменов — источник ложных нарушений: «нет ИД» не является нарушением.
В сводное число нарушений входит ровно один статус: CONFIRMED_VIOLATION.
"""

from __future__ import annotations

from enum import StrEnum


class Completeness(StrEnum):
    """Комплектность стадии. Отдельно от находок (ТЗ п. 9.1)."""

    UPLOADED = "UPLOADED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


class ProcessState(StrEnum):
    """Жизненный цикл проверки (ТЗ п. 9.1)."""

    PENDING = "PENDING"
    PARSING = "PARSING"
    READY = "READY"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FINALIZED = "FINALIZED"


class Scenario(StrEnum):
    """Сценарий загрузки (ТЗ п. 9.2). Определяет применимость, не нарушения."""

    FULL = "FULL"
    PD_RD_ONLY = "PD_RD_ONLY"
    PD_ID_ONLY = "PD_ID_ONLY"
    RD_ID_ONLY = "RD_ID_ONLY"
    SINGLE_ONLY = "SINGLE_ONLY"
    PARTIALLY_LOADED = "PARTIALLY_LOADED"


class FindingStatus(StrEnum):
    """Статус находки.

    AUTO_NO_DIFFERENCE — автоматическое «расхождения нет». В GOLD переводится
    только после решения инспектора, который присваивает NEGATIVE_VERIFIED
    (расхождение п. 9.2 и 9.3 ТЗ, вопрос 8 организатору).
    """

    CANDIDATE = "CANDIDATE"
    CONFIRMED_VIOLATION = "CONFIRMED_VIOLATION"
    NEGATIVE_VERIFIED = "NEGATIVE_VERIFIED"
    AUTO_NO_DIFFERENCE = "AUTO_NO_DIFFERENCE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    LOW_QUALITY = "LOW_QUALITY"
    ABSTAIN = "ABSTAIN"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    SUSPICION = "SUSPICION"


#: Единственный статус, входящий в сводное число нарушений.
VIOLATION_STATUSES: frozenset[FindingStatus] = frozenset({FindingStatus.CONFIRMED_VIOLATION})

#: Статусы качества данных: не нарушения и не «пройдено».
DATA_QUALITY_STATUSES: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.MISSING_EVIDENCE,
        FindingStatus.NOT_APPLICABLE,
        FindingStatus.NOT_COMPARABLE,
        FindingStatus.LOW_QUALITY,
        FindingStatus.ABSTAIN,
        FindingStatus.CLARIFICATION_REQUIRED,
    }
)

#: Статусы, которые машина не имеет права присвоить без инспектора.
HUMAN_ONLY_STATUSES: frozenset[FindingStatus] = frozenset(
    {FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED}
)

#: Карточки, которые можно отдать во внешний протокол ТЗ и в РиН.
#: AUTO_NO_DIFFERENCE живёт только внутри до ответа на вопрос 8.
WIRE_FINDING_STATUSES: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.CANDIDATE,
        FindingStatus.CONFIRMED_VIOLATION,
        FindingStatus.NEGATIVE_VERIFIED,
        FindingStatus.MISSING_EVIDENCE,
        FindingStatus.NOT_APPLICABLE,
        FindingStatus.NOT_COMPARABLE,
        FindingStatus.LOW_QUALITY,
        FindingStatus.ABSTAIN,
        FindingStatus.CLARIFICATION_REQUIRED,
        FindingStatus.SUSPICION,
    }
)

#: Предметный статус без evidence_group_id не существует (ADR-0002).
STATUSES_REQUIRING_EVIDENCE: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.CANDIDATE,
        FindingStatus.CONFIRMED_VIOLATION,
        FindingStatus.NEGATIVE_VERIFIED,
        FindingStatus.AUTO_NO_DIFFERENCE,
    }
)


class ReasonCode(StrEnum):
    """Кодированная причина отклонения кандидата (ТЗ п. 9.3, обязательна)."""

    WRONG_REVISION_SELECTED = "WRONG_REVISION_SELECTED"
    APPROVED_CHANGE_EXISTS = "APPROVED_CHANGE_EXISTS"
    OCR_ERROR = "OCR_ERROR"
    LINKAGE_ERROR = "LINKAGE_ERROR"
    PARAMETER_NOT_APPLICABLE = "PARAMETER_NOT_APPLICABLE"
    SOURCE_QUALITY = "SOURCE_QUALITY"
    OTHER = "OTHER"


class SyncState(StrEnum):
    """Синхронизация с внешней ИС. Сбой передачи не меняет решение инспектора."""

    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING_SYNC = "PENDING_SYNC"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED_TERMINAL = "FAILED_TERMINAL"


class ReviewPriority(StrEnum):
    """Очередь экспертной проверки. Не юридическая тяжесть (ТЗ п. 8.1, 9.2)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
