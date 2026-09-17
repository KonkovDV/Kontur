"""Резолвер актуальной утверждённой редакции (Gate E, ТЗ п. 9.1).

Инвариант: эталоном сравнения является только последняя утверждённая редакция.
Неутверждённая редакция, даже если она новее, не становится эталоном.
Конфликт predecessor/successor → RevisionConflict (→ CLARIFICATION_REQUIRED).

Связанные требования ТЗ:
- п. 9.1: «актуальная утверждённая редакция»
- п. 9.2: «расхождение — только между утверждёнными стадиями»
- ADR-0005: машины состояний не выносят юридических решений
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import FindingStatus


class RevisionConflict(ValueError):
    """Граф редакций содержит неоднозначность или цикл.

    Вызывающий слой обязан закрыть находку через CLARIFICATION_REQUIRED
    и зафиксировать conflict_reason в rationale.
    """


@dataclass(frozen=True, slots=True)
class ResolvedRevision:
    """Одна утверждённая редакция, выбранная как эталон сравнения."""

    document: DocumentRef
    #: True, если документ заменён более новой утверждённой редакцией.
    is_stale: bool = False


@dataclass(frozen=True, slots=True)
class RevisionResolution:
    """Итог резолвера для одного параметра / одной стадии.

    status:
      AUTO_NO_DIFFERENCE     — успешный выбор эталона
      MISSING_EVIDENCE       — нет документов стадии вообще
      CLARIFICATION_REQUIRED — нет ни одной утверждённой редакции
    resolved — None при любом нетерминальном статусе.
    """

    status: FindingStatus
    resolved: ResolvedRevision | None
    conflict_reason: str | None = None


def _is_approved(doc: DocumentRef) -> bool:
    return doc.approval_status is ApprovalStatus.APPROVED


def resolve_revision(
    documents: list[DocumentRef],
    stage: DocStage,
) -> RevisionResolution:
    """Выбирает последнюю утверждённую редакцию для стадии.

    Алгоритм:
    1. Фильтр: только документы нужной стадии.
    2. Фильтр: только APPROVED — неутверждённые вход в approved-пул не попадают.
    3. Ищем «голову» цепочки: approved без successor_file_id
       ИЛИ чей successor_file_id не является approved.
    4. Если голов несколько — RevisionConflict.
    5. Случай цикла — RevisionConflict.
    6. Неутверждённая редакция не вытесняет утверждённую (RT-2709-08).
    """
    stage_docs = [d for d in documents if d.doc_stage is stage]
    if not stage_docs:
        return RevisionResolution(
            status=FindingStatus.MISSING_EVIDENCE,
            resolved=None,
            conflict_reason=f"нет документов стадии {stage}",
        )

    approved = [d for d in stage_docs if _is_approved(d)]
    if not approved:
        return RevisionResolution(
            status=FindingStatus.CLARIFICATION_REQUIRED,
            resolved=None,
            conflict_reason=(
                f"нет утверждённых редакций для {stage}"
                f" ({len(stage_docs)} неутверждённых)"
            ),
        )

    approved_ids: frozenset[str] = frozenset(d.file_id for d in approved)

    # Голова: approved без successor_file_id ИЛИ чей successor не approved
    heads = [
        d for d in approved
        if d.successor_file_id is None or d.successor_file_id not in approved_ids
    ]

    if len(heads) == 0:
        ids = ", ".join(d.file_id for d in approved)
        raise RevisionConflict(
            f"цикл в графе редакций для {stage}: {ids}"
        )

    if len(heads) > 1:
        ids = ", ".join(d.file_id for d in heads)
        raise RevisionConflict(
            f"несколько утверждённых редакций без однозначного successor"
            f" для {stage}: {ids}"
        )

    return RevisionResolution(
        status=FindingStatus.AUTO_NO_DIFFERENCE,
        resolved=ResolvedRevision(document=heads[0], is_stale=False),
    )


def check_stale_revision(
    candidate: DocumentRef,
    all_documents: list[DocumentRef],
) -> bool:
    """True если candidate устарел: заменён более новой APPROVED редакцией.

    Неутверждённый successor не считается: сокращает FPR (RT-2609-17).
    """
    successors = [
        d
        for d in all_documents
        if d.doc_stage is candidate.doc_stage
        and d.file_id != candidate.file_id
        and _is_approved(d)
        and d.predecessor_file_id == candidate.file_id
        and d.approval_date is not None
        and candidate.approval_date is not None
        and d.approval_date > candidate.approval_date
    ]
    return bool(successors)
