"""Верификация инспектором (ТЗ п. 9.3).

Единственное место, где находка получает CONFIRMED_VIOLATION или
NEGATIVE_VERIFIED. Вызов из фоновой задачи, автомата или модели отклоняется.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from kontur.application.revision_resolver import overlay_inspector_approval
from kontur.domain.models import ApprovalStatus, EvidenceGroup, Finding, InspectorDecision
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

MASS_CONFIRM_LIMIT = 50

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


def confirm_candidates(
    findings: Sequence[Finding],
    *,
    actor: Actor,
    comment: str,
) -> tuple[Finding, ...]:
    """Пачка только из CANDIDATE. Отказ и чужой статус не применяются вовсе.

    Массового отклонения нет: действие всегда CONFIRM. Пустой список и повтор
    идентификатора не пишут ни одной находки.
    """

    if not findings:
        raise TransitionError("пустой список подтверждения")
    if len(findings) > MASS_CONFIRM_LIMIT:
        raise TransitionError(f"пачка больше {MASS_CONFIRM_LIMIT} находок")
    ids = [item.finding_id for item in findings]
    if len(ids) != len(set(ids)):
        raise TransitionError("повтор finding_id в пачке")
    if not actor.is_human:
        raise TransitionError("массовое подтверждение требует инспектора")
    for item in findings:
        if item.finding_status is not FindingStatus.CANDIDATE:
            raise TransitionError(f"{item.finding_id}: массово подтверждается только CANDIDATE")
    return tuple(review(item, actor=actor, action="CONFIRM", comment=comment) for item in findings)


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

    CANDIDATE блокирует. SUSPICION не блокирует: инспектор принимает
    или отклоняет гипотезу, а протокол можно собрать и без этого.
    CLARIFICATION_REQUIRED не блокирует: п. 9.3 и OpenAPI явно допускают
    перевод кандидата в уточнение как способ закрыть очередь.
    MISSING_EVIDENCE выводится отдельным перечнем и не блокирует.
    """

    blocking = {FindingStatus.CANDIDATE}
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


def split(
    finding: Finding,
    parts: Sequence[EvidenceGroup],
    *,
    actor: Actor,
) -> list[Finding]:
    """Разделить составного кандидата на атомарные находки (ТЗ п. 9.3).

    Общего статуса PARTIALLY_CONFIRMED нет. У каждой части своё доказательство
    и потом своё решение инспектора. Автомат эту функцию не вызывает.
    """

    if not actor.is_human:
        raise TransitionError("разделение требует инспектора")
    if finding.finding_status is not FindingStatus.CANDIDATE:
        raise TransitionError("делится только кандидат")
    if len(parts) < 2:
        raise TransitionError("нужны минимум две части со своими доказательствами")
    seen: set[str] = set()
    created: list[Finding] = []
    for index, group in enumerate(parts, start=1):
        if not group.fragments:
            raise TransitionError("у части нет доказательства")
        if group.rule_code != finding.rule_code:
            raise TransitionError("часть относится к другому правилу")
        if group.evidence_group_id in seen:
            raise TransitionError("у частей один evidence_group_id")
        seen.add(group.evidence_group_id)
        created.append(
            replace(
                finding,
                finding_id=f"{finding.finding_id}:{index}",
                evidence_group_id=group.evidence_group_id,
                evidence_refs=tuple(item.fragment_id for item in group.fragments),
                inspector_decision=None,
            )
        )
    return created
