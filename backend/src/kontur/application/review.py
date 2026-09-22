"""Верификация инспектором (ТЗ п. 9.3).

Единственное место, где находка получает CONFIRMED_VIOLATION или
NEGATIVE_VERIFIED. Вызов из фоновой задачи, автомата или модели отклоняется.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

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


# ---------------------------------------------------------------------------
# GAP-SPLIT (#83)
# ---------------------------------------------------------------------------

_SPLITTABLE_STATUSES: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.CANDIDATE,
        FindingStatus.CLARIFICATION_REQUIRED,
    }
)


def split(
    finding: Finding,
    parts: int,
    *,
    actor: Actor,
    audit: AuditLog,
    process_state: ProcessState | None = None,
) -> list[Finding]:
    """Атомарный split составного кандидата (ТЗ п. 9.3, #83 GAP-SPLIT).

    Каждая из N частей получает:
    - новый finding_id = ``<parent>__split_NN_<hex8>``;
    - новый evidence_group_id-заглушку — инспектор заполняет через API;
    - source_id = родительский finding_id (цепочка провенанса, ADR-0002);
    - evidence_refs = () — провенанс не дублируется;
    - finding_status = CANDIDATE;
    - inspector_decision = None.

    Инварианты (fail-closed, SOTA 2026):
    - только человек (actor.is_human);
    - только CANDIDATE или CLARIFICATION_REQUIRED;
    - запрещён после FINALIZED;
    - parts >= 2.

    SPLIT не является атомарным action в ReviewDecision:
    review() отклоняет SPLIT через TransitionError.
    """
    if not actor.is_human:
        raise TransitionError("split requires a human inspector")
    if parts < 2:  # noqa: PLR2004
        raise TransitionError(f"split requires parts >= 2, got {parts}")
    if finding.finding_status not in _SPLITTABLE_STATUSES:
        raise TransitionError(
            f"split: нельзя разделить finding в статусе {finding.finding_status}; "
            "ожидается CANDIDATE или CLARIFICATION_REQUIRED"
        )
    if process_state is ProcessState.FINALIZED:
        raise TransitionError("split: запрещён после FINALIZED")

    result: list[Finding] = []
    for i in range(parts):
        suffix = f"split_{i + 1:02d}_{uuid4().hex[:8]}"
        part = replace(
            finding,
            finding_id=f"{finding.finding_id}__{suffix}",
            # Placeholder: инспектор добавит реальную evidence_group через API
            evidence_group_id=f"eg_{suffix}",
            source_id=finding.finding_id,
            evidence_refs=(),
            inspector_decision=None,
            finding_status=FindingStatus.CANDIDATE,
        )
        result.append(part)

    audit.record(
        actor.actor_id,
        "SPLIT",
        {
            "parent_finding_id": finding.finding_id,
            "parts": parts,
            "child_ids": [f.finding_id for f in result],
        },
    )
    return result
