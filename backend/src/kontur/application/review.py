"""Верификация инспектором (ТЗ п. 9.3).

Единственное место, где находка получает CONFIRMED_VIOLATION или
NEGATIVE_VERIFIED. Вызов из фоновой задачи, автомата или модели отклоняется.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from kontur.domain.models import Finding, InspectorDecision
from kontur.domain.state_machines import Actor, TransitionError, advance_finding
from kontur.domain.statuses import FindingStatus, ReasonCode

ACTION_TO_STATUS: dict[str, FindingStatus] = {
    "CONFIRM": FindingStatus.CONFIRMED_VIOLATION,
    "REJECT": FindingStatus.NEGATIVE_VERIFIED,
    "REQUEST_CLARIFICATION": FindingStatus.CLARIFICATION_REQUIRED,
}


def review(
    finding: Finding,
    *,
    actor: Actor,
    action: str,
    reason_code: ReasonCode | None = None,
    comment: str | None = None,
) -> Finding:
    """Применяет решение инспектора к атомарной находке."""

    if action not in ACTION_TO_STATUS:
        raise TransitionError(f"unknown review action: {action}")
    if action == "REJECT" and reason_code is None:
        # ТЗ п. 9.3: отклонение без кодированной причины не принимается.
        raise TransitionError("REJECT requires reason_code")

    target = ACTION_TO_STATUS[action]
    advance_finding(finding.finding_status, target, actor)

    decision = InspectorDecision(
        inspector_id=actor.actor_id,
        action=action,
        timestamp=datetime.now(tz=UTC),
        reason_code=reason_code,
        comment=comment,
    )
    return replace(finding, finding_status=target, inspector_decision=decision)


def can_finalize(findings: list[Finding]) -> tuple[bool, list[str]]:
    """Финализация разрешена только после обработки всех кандидатов.

    MISSING_EVIDENCE выводится отдельным перечнем и не блокирует финализацию.
    """

    pending = [f.finding_id for f in findings if f.finding_status is FindingStatus.CANDIDATE]
    return (not pending, pending)


def split(finding: Finding, parts: int) -> list[Finding]:
    """Разделение составного кандидата на атомарные (ТЗ п. 9.3).

    Общего статуса PARTIALLY_CONFIRMED не существует: каждая часть получает
    собственное доказательство и собственное решение.
    """

    raise NotImplementedError("L8: каждая часть требует собственной evidence_group")
