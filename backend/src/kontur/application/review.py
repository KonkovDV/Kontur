"""Верификация инспектором (ТЗ п. 9.3).

Единственное место, где находка получает CONFIRMED_VIOLATION или
NEGATIVE_VERIFIED. Вызов из фоновой задачи, автомата или модели отклоняется.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from kontur.application.revision_resolver import overlay_inspector_approval
from kontur.domain.models import ApprovalStatus, Finding, InspectorDecision
from kontur.domain.ports import AuditLog
from kontur.domain.state_machines import (
    Actor,
    TransitionError,
    advance_finding,
    enter_completed,
    enter_finalized,
    enter_verifying,
    unfinalize,
)
from kontur.domain.statuses import FindingStatus, ProcessState, ReasonCode

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

    if action == "SPLIT":
        raise TransitionError("SPLIT is not an atomic review action; use split()")
    if action not in ACTION_TO_STATUS:
        raise TransitionError(f"unknown review action: {action}")
    if action == "REJECT" and reason_code is None:
        raise TransitionError("REJECT requires reason_code")
    if comment is None or not comment.strip():
        raise TransitionError("review action requires comment")

    target = ACTION_TO_STATUS[action]
    advance_finding(finding.finding_status, target, actor)

    decision = InspectorDecision(
        inspector_id=actor.actor_id,
        action=action,
        timestamp=datetime.now(tz=UTC),
        reason_code=reason_code,
        comment=comment.strip(),
    )
    return replace(finding, finding_status=target, inspector_decision=decision)


def start_verification(
    current: ProcessState,
    *,
    actor: Actor,
    audit: AuditLog,
) -> ProcessState:
    """Инспектор открывает очередь: READY → VERIFYING."""

    if not actor.is_human:
        raise TransitionError("start verification requires a human inspector")
    target = enter_verifying(current, actor)
    audit.record(
        actor.actor_id,
        "START_VERIFICATION",
        {"from": current.value, "to": target.value},
    )
    return target


def complete_verification(
    current: ProcessState,
    *,
    actor: Actor,
    findings: list[Finding],
    audit: AuditLog,
) -> ProcessState:
    """Инспектор закрывает очередь: VERIFYING → COMPLETED. Не FINALIZED."""

    if not actor.is_human:
        raise TransitionError("complete verification requires a human inspector")
    ok, pending = can_finalize(findings)
    if not ok:
        raise TransitionError(f"unprocessed findings: {pending}")
    target = enter_completed(current, actor)
    audit.record(
        actor.actor_id,
        "COMPLETE_VERIFICATION",
        {"from": current.value, "to": target.value},
    )
    return target


def can_finalize(findings: list[Finding]) -> tuple[bool, list[str]]:
    """Финализация — после обработки всех кандидатов и подозрений.

    CANDIDATE блокирует. SUSPICION блокирует: это необработанный сигнал.
    CLARIFICATION_REQUIRED не блокирует: п. 9.3 и OpenAPI явно допускают
    перевод кандидата в уточнение как способ закрыть очередь.
    MISSING_EVIDENCE выводится отдельным перечнем и не блокирует.
    """

    blocking = {
        FindingStatus.CANDIDATE,
        FindingStatus.SUSPICION,
    }
    pending = [f.finding_id for f in findings if f.finding_status in blocking]
    return (not pending, pending)


def finalize_process(
    current: ProcessState,
    *,
    actor: Actor,
    findings: list[Finding],
    audit: AuditLog,
) -> ProcessState:
    """Финализация протокола: человек, закрытая очередь, запись в журнал."""

    if not actor.is_human:
        raise TransitionError("finalize requires a human inspector")
    ok, pending = can_finalize(findings)
    if not ok:
        raise TransitionError(f"unprocessed findings: {pending}")
    target = enter_finalized(current, actor)
    audit.record(
        actor.actor_id,
        "FINALIZE",
        {"from": current.value, "to": target.value},
    )
    return target


def unfinalize_process(
    current: ProcessState,
    *,
    actor: Actor,
    reason: str,
    audit: AuditLog,
) -> ProcessState:
    """Отмена финализации с причиной и аудитом. Новую версию протокола пишет L9."""

    target = unfinalize(current, actor, reason)
    audit.record(
        actor.actor_id,
        "UNFINALIZE",
        {"from": current.value, "to": target.value, "reason": reason.strip()},
    )
    return target


def select_revision_as_etalon(
    *,
    actor: Actor,
    stamp: ApprovalStatus,
    comment: str,
) -> ApprovalStatus:
    """Инспектор назначает загруженный документ эталоном сравнения.

    Это не CONFIRMED_VIOLATION и не эвристика «ГИП = утверждено». Автомат
    не вызывает функцию. Явный отказ в штампе нельзя перекрыть.
    """

    if not actor.is_human:
        raise TransitionError("выбор эталона требует инспектора")
    if not comment.strip():
        raise TransitionError("выбор эталона требует comment")
    if stamp is ApprovalStatus.NOT_APPROVED:
        raise TransitionError(
            "явный отказ в утверждении нельзя перекрыть выбором инспектора"
        )
    return overlay_inspector_approval(stamp, inspector_selected=True)


def split(finding: Finding, parts: int) -> list[Finding]:
    """Разделение составного кандидата на атомарные (ТЗ п. 9.3).

    Общего статуса PARTIALLY_CONFIRMED не существует: каждая часть получает
    собственное доказательство и собственное решение.
    """

    raise NotImplementedError("L8: каждая часть требует собственной evidence_group")
