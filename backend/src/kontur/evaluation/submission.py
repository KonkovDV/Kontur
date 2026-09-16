"""Два провода статусов: внутренний FindingStatus и внешний submission хакатона.

Домен не подгоняется под enum организатора. Этот модуль — адаптер границы
соревнования: `submission_schema.json`. Провод ТЗ/РиН по-прежнему идёт через
`status_map.on_the_wire` и не содержит AUTO_NO_DIFFERENCE.
"""

from __future__ import annotations

from enum import StrEnum

from kontur.domain.statuses import WIRE_FINDING_STATUSES, FindingStatus


class ContestViolationLabel(StrEnum):
    """`violation_label` из submission_schema.json организатора."""

    VIOLATION_PRESENT = "VIOLATION_PRESENT"
    NO_VIOLATION = "NO_VIOLATION"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    COMPARISON_IMPOSSIBLE = "COMPARISON_IMPOSSIBLE"


class ContestProtocolStatus(StrEnum):
    """`protocol_status` из submission_schema.json. Не FindingStatus и не review_priority."""

    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    ID_MISSING = "ID_MISSING"
    RD_MISSING = "RD_MISSING"
    PD_MISSING = "PD_MISSING"
    COMPARISON_IMPOSSIBLE = "COMPARISON_IMPOSSIBLE"


# Команда на хакатоне заявляет детекцию. CANDIDATE — это её VIOLATION_PRESENT.
# AUTO_NO_DIFFERENCE на провод ТЗ не отдаётся, но в JSON участника становится
# NO_VIOLATION: иначе 5 gold-проверок с violation_label=NO_VIOLATION некуда класть.
_CONTEST_LABEL: dict[FindingStatus, ContestViolationLabel] = {
    FindingStatus.CANDIDATE: ContestViolationLabel.VIOLATION_PRESENT,
    FindingStatus.CONFIRMED_VIOLATION: ContestViolationLabel.VIOLATION_PRESENT,
    FindingStatus.NEGATIVE_VERIFIED: ContestViolationLabel.NO_VIOLATION,
    FindingStatus.AUTO_NO_DIFFERENCE: ContestViolationLabel.NO_VIOLATION,
    FindingStatus.MISSING_EVIDENCE: ContestViolationLabel.MISSING_DOCUMENT,
    FindingStatus.NOT_APPLICABLE: ContestViolationLabel.NO_VIOLATION,
    FindingStatus.NOT_COMPARABLE: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.LOW_QUALITY: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.ABSTAIN: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.CLARIFICATION_REQUIRED: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.SUSPICION: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
}


def contest_violation_label(status: FindingStatus) -> ContestViolationLabel:
    """Внутренний статус → метка JSON участника. Не используется для РиН."""

    try:
        return _CONTEST_LABEL[status]
    except KeyError as exc:
        raise ValueError(f"нет маппинга на submission_schema для {status}") from exc


def contest_allows_auto_no_difference() -> bool:
    """Напоминание инварианта: два провода расходятся на AUTO_NO_DIFFERENCE."""

    return FindingStatus.AUTO_NO_DIFFERENCE not in WIRE_FINDING_STATUSES
