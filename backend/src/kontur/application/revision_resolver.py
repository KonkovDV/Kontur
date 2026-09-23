"""Резолвер актуальной редакции (Gate E, ТЗ п. 9.1, ADR-0014).

ПД без явного «не утв.» — эталон комплекта, если голова шифра одна.
РД и ИД не требуют графы «Утвердил». `NOT_APPROVED` в пул не входит.
Несколько голов или цикл — `CLARIFICATION_REQUIRED`, без сравнения.

Резолвер не пишет `finding_status` сравнения: успешный выбор эталона — это
не «расхождения нет».
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from kontur.domain.models import ApprovalBasis, ApprovalStatus, DocStage, DocumentRef


def _same_document_identity(left: DocumentRef, right: DocumentRef) -> bool:
    """Цепочка редакций — один документ, не все файлы стадии (ADR-0003)."""

    if left.doc_stage is not right.doc_stage:
        return False
    if left.document_code and right.document_code and left.document_code != right.document_code:
        return False
    if left.sheet and right.sheet and left.sheet != right.sheet:
        return False
    if left.discipline and right.discipline and left.discipline != right.discipline:
        return False
    return True


class RevisionConflict(ValueError):
    """Граф редакций содержит неоднозначность или цикл.

    Вызывающий слой обязан закрыть находку через CLARIFICATION_REQUIRED
    и зафиксировать conflict_reason в rationale.
    """


class ResolveStatus(StrEnum):
    """Исход выбора эталона. Это не статус находки."""

    RESOLVED = "RESOLVED"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class ResolvedRevision:
    """Одна утверждённая редакция, выбранная как эталон сравнения."""

    document: DocumentRef
    #: True, если документ заменён более новой утверждённой редакцией.
    is_stale: bool = False


@dataclass(frozen=True, slots=True)
class RevisionResolution:
    """Итог резолвера для одной стадии."""

    status: ResolveStatus
    resolved: ResolvedRevision | None
    conflict_reason: str | None = None


def _eligible(doc: DocumentRef) -> bool:
    """В пул головы входит всё, кроме явного «не утв.»."""

    return doc.approval_status is not ApprovalStatus.NOT_APPROVED


def package_etalon(doc: DocumentRef) -> DocumentRef:
    """Единственная голова ПД без штампа — эталон комплекта, не TITLE_BLOCK."""

    if doc.doc_stage is DocStage.PD and doc.approval_status is ApprovalStatus.UNKNOWN:
        return replace(
            doc,
            approval_status=ApprovalStatus.APPROVED,
            approval_basis=ApprovalBasis.PACKAGE_DEFAULT,
        )
    return doc


def overlay_inspector_approval(
    stamp: ApprovalStatus,
    *,
    inspector_selected: bool,
) -> ApprovalStatus:
    """Инспектор может назначить эталоном документ со штампом UNKNOWN.

    Явный `NOT_APPROVED` (черновик / «не утв.») нельзя перекрыть. Штамп с
    заполненной графой «Утвердил»+ФИО остаётся APPROVED и без выбора.
    Выбор инспектора не подменяет штамп и не закрывает гейт J.
    """

    if stamp is ApprovalStatus.NOT_APPROVED:
        return ApprovalStatus.NOT_APPROVED
    if inspector_selected:
        return ApprovalStatus.APPROVED
    return stamp


def approval_with_basis(
    stamp: ApprovalStatus,
    basis: ApprovalBasis,
    *,
    inspector_selected: bool,
) -> tuple[ApprovalStatus, ApprovalBasis]:
    """Выбор инспектора меняет basis только если штамп сам не доказал утверждение."""

    status = overlay_inspector_approval(stamp, inspector_selected=inspector_selected)
    if (
        inspector_selected
        and stamp is ApprovalStatus.UNKNOWN
        and status is ApprovalStatus.APPROVED
    ):
        return status, ApprovalBasis.INSPECTOR_SELECT
    return status, basis


def resolve_revision(
    documents: list[DocumentRef],
    stage: DocStage,
    *,
    anchor: DocumentRef | None = None,
) -> RevisionResolution:
    """Выбирает последнюю утверждённую редакцию для стадии.

    1. Только документы нужной стадии.
    2. При `anchor` — только та же identity (шифр, лист, раздел).
    3. `NOT_APPROVED` в пул голов не попадает. ПД без штампа остаётся кандидатом.
    4. Голова: нет successor в пуле пригодных редакций.
    5. Одна голова ПД без штампа получает `PACKAGE_DEFAULT`.
    6. Несколько голов или цикл — RevisionConflict.
    """

    stage_docs = [item for item in documents if item.doc_stage is stage]
    if anchor is not None:
        if anchor.doc_stage is not stage:
            return RevisionResolution(
                status=ResolveStatus.MISSING_EVIDENCE,
                resolved=None,
                conflict_reason=(
                    f"якорь {anchor.file_id} стадии {anchor.doc_stage.value},"
                    f" запрошена {stage.value}"
                ),
            )
        stage_docs = [item for item in stage_docs if _same_document_identity(anchor, item)]
    if not stage_docs:
        return RevisionResolution(
            status=ResolveStatus.MISSING_EVIDENCE,
            resolved=None,
            conflict_reason=f"нет документов стадии {stage.value}",
        )

    eligible = [item for item in stage_docs if _eligible(item)]
    if not eligible:
        return RevisionResolution(
            status=ResolveStatus.CLARIFICATION_REQUIRED,
            resolved=None,
            conflict_reason=(
                f"нет редакции без явного «не утв.» для {stage.value}"
                f" ({len(stage_docs)} отклонено)"
            ),
        )

    eligible_ids: frozenset[str] = frozenset(item.file_id for item in eligible)
    heads = [
        item
        for item in eligible
        if item.successor_file_id is None or item.successor_file_id not in eligible_ids
    ]
    if len(heads) == 0:
        ids = ", ".join(item.file_id for item in eligible)
        raise RevisionConflict(f"цикл в графе редакций для {stage.value}: {ids}")
    if len(heads) > 1:
        ids = ", ".join(item.file_id for item in heads)
        raise RevisionConflict(
            f"несколько редакций без однозначного successor для {stage.value}: {ids}"
        )
    return RevisionResolution(
        status=ResolveStatus.RESOLVED,
        resolved=ResolvedRevision(document=package_etalon(heads[0]), is_stale=False),
    )


def check_stale_revision(
    candidate: DocumentRef,
    all_documents: list[DocumentRef],
) -> bool:
    """True, если candidate заменён более новой APPROVED редакцией.

    Неутверждённый successor не считается: он не смещает эталон (RT-2709-08).
    Связь predecessor/successor первична; даты не требуются.
    """

    return any(
        item.doc_stage is candidate.doc_stage
        and item.file_id != candidate.file_id
        and _eligible(item)
        and item.predecessor_file_id == candidate.file_id
        for item in all_documents
    )
