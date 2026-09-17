"""Сигналы подозрения вне автоматического вердикта (ТЗ п. 9.5, RT-2609-16).

SUSPICION — гипотеза для инспектора, не строка матрицы и не нарушение.
Автомат, LLM и этот модуль не имеют права записать CONFIRMED_VIOLATION
(ADR-0001). Расхождение двух чтений критического значения в компараторе
по-прежнему даёт ABSTAIN; здесь только параллельный сигнал в очередь.
Сверка с СНиП/СанПиН не является подходом (ADR-0006).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from kontur.domain.statuses import FindingStatus

DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.60


class SuspicionApproach(StrEnum):
    """Четыре подхода п. 9.5. Это не статусы находки и не операторы матрицы."""

    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    DUAL_READ_DISAGREE = "DUAL_READ_DISAGREE"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    ANNOTATION_CONFLICT = "ANNOTATION_CONFLICT"


@dataclass(frozen=True, slots=True)
class SuspicionSignal:
    """Один сигнал на (rule_code, evidence_group_id). Статус всегда SUSPICION."""

    rule_code: str
    evidence_group_id: str
    approach: SuspicionApproach
    confidence: float
    detail: str
    status: FindingStatus = FindingStatus.SUSPICION

    def __post_init__(self) -> None:
        if not self.evidence_group_id.strip():
            raise ValueError("evidence_group_id обязателен для SUSPICION (ADR-0002)")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence должен быть в [0; 1]")
        if self.status is not FindingStatus.SUSPICION:
            raise ValueError("status сигнала может быть только SUSPICION")
        if not self.rule_code.strip():
            raise ValueError("rule_code не может быть пустым")


def assess_low_confidence(
    rule_code: str,
    evidence_group_id: str,
    *,
    confidence: float,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> SuspicionSignal | None:
    """Подход 1: извлечённое значение есть, уверенность ниже порога."""

    if confidence >= low_confidence_threshold:
        return None
    return SuspicionSignal(
        rule_code,
        evidence_group_id,
        SuspicionApproach.LOW_CONFIDENCE,
        confidence,
        detail=f"уверенность {confidence:.2f} ниже порога {low_confidence_threshold:.2f}",
    )


def assess_dual_read_disagree(
    rule_code: str,
    evidence_group_id: str,
    *,
    first_value: object,
    second_value: object,
) -> SuspicionSignal | None:
    """Подход 2: два чтения разошлись.

    Не заменяет ABSTAIN компаратора и не эскалирует в CANDIDATE/CONFIRMED.
    """

    if first_value == second_value:
        return None
    return SuspicionSignal(
        rule_code,
        evidence_group_id,
        SuspicionApproach.DUAL_READ_DISAGREE,
        0.50,
        detail=f"двойное чтение разошлось: {first_value!s} ≠ {second_value!s}",
    )


def assess_partial_match(
    rule_code: str,
    evidence_group_id: str,
    *,
    matched_criteria: int,
    total_criteria: int,
) -> SuspicionSignal | None:
    """Подход 3: часть критериев совпала. PARTIALLY_CONFIRMED в домене нет."""

    if total_criteria <= 0:
        return None
    if matched_criteria <= 0 or matched_criteria >= total_criteria:
        return None
    ratio = matched_criteria / total_criteria
    return SuspicionSignal(
        rule_code,
        evidence_group_id,
        SuspicionApproach.PARTIAL_MATCH,
        ratio,
        detail=f"{matched_criteria}/{total_criteria} критериев совпали",
    )


def assess_annotation_conflict(
    rule_code: str,
    evidence_group_id: str,
    *,
    conflict_description: str,
) -> SuspicionSignal | None:
    """Подход 4: конфликт разметок/редакций одного доказательства."""

    detail = conflict_description.strip()
    if not detail:
        return None
    return SuspicionSignal(
        rule_code,
        evidence_group_id,
        SuspicionApproach.ANNOTATION_CONFLICT,
        0.70,
        detail=detail,
    )


def deduplicate_by_group(signals: Sequence[SuspicionSignal]) -> tuple[SuspicionSignal, ...]:
    """Один сигнал на (rule_code, evidence_group_id): оставляем больший confidence."""

    chosen: dict[tuple[str, str], SuspicionSignal] = {}
    for signal in signals:
        key = (signal.rule_code, signal.evidence_group_id)
        current = chosen.get(key)
        if current is None or signal.confidence > current.confidence:
            chosen[key] = signal
    return tuple(chosen.values())
