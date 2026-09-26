"""Резолвер актуальной редакции (Gate E, ТЗ п. 9.1, ответ организатора 26.09).

ПД без сведений об утверждении — `CLARIFICATION_REQUIRED`, не эталон.
РД и ИД не требуют графы «Утвердил». `NOT_APPROVED` в пул не входит.
Несколько голов или цикл — `CLARIFICATION_REQUIRED`, без сравнения.

Резолвер не пишет `finding_status` сравнения: успешный выбор эталона — это
не «расхождения нет».
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from kontur.domain.models import ApprovalBasis, ApprovalStatus, DocStage, DocumentRef


def _identity_key(doc: DocumentRef) -> tuple[str, str, str] | None:
    """Шифр + лист + раздел. Пустой шифр не доказывает совпадение с другим файлом."""

    if not doc.document_code:
        return None
    return (doc.document_code, doc.sheet or "", doc.discipline or "")


def _reject_mixed_identities(docs: list[DocumentRef], stage: DocStage) -> None:
    """Разные документы стадии — не цепочка редакций одного шифра (ADR-0003)."""

    known = {key for item in docs if (key := _identity_key(item)) is not None}
    if len(known) > 1:
        labels = ", ".join(sorted({key[0] for key in known}))
        raise RevisionConflict(
            f"несколько документов стадии {stage.value}, не цепочка одного шифра: {labels}"
        )
    if known and any(_identity_key(item) is None for item in docs):
        raise RevisionConflict(
            f"шифр части файлов стадии {stage.value} не прочитан, цепочка не строится"
        )


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


def _finish_head(
    chosen: DocumentRef,
    eligible: list[DocumentRef],
    *,
    inspector_selected: bool,
) -> RevisionResolution:
    """ПД без сведений об утверждении не становится эталоном сама.

    Выбор инспектора переводит UNKNOWN в APPROVED с INSPECTOR_SELECT.
    РД и ИД сравнение не останавливают.
    """

    if (
        inspector_selected
        and chosen.doc_stage is DocStage.PD
        and chosen.approval_status is ApprovalStatus.UNKNOWN
    ):
        status, basis = approval_with_basis(
            chosen.approval_status,
            chosen.approval_basis,
            inspector_selected=True,
        )
        chosen = replace(chosen, approval_status=status, approval_basis=basis)
    elif chosen.doc_stage is DocStage.PD and chosen.approval_status is ApprovalStatus.UNKNOWN:
        return RevisionResolution(
            status=ResolveStatus.CLARIFICATION_REQUIRED,
            resolved=None,
            conflict_reason="сведения об утверждении отсутствуют",
        )
    return RevisionResolution(
        status=ResolveStatus.RESOLVED,
        resolved=ResolvedRevision(
            document=chosen,
            is_stale=check_stale_revision(chosen, eligible),
        ),
    )


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
    inspector_selected_file_ids: frozenset[str] = frozenset(),
) -> RevisionResolution:
    """Выбирает последнюю утверждённую редакцию для стадии.

    1. Только документы нужной стадии.
    2. При `anchor` — только та же identity (шифр, лист, раздел).
    3. `NOT_APPROVED` в пул голов не попадает. ПД без штампа остаётся кандидатом.
    4. Разные шифры или лист/раздел — не одна цепочка. Выбор инспектора
       чужой документ не поглощает.
    5. Ровно один пригодный файл из `inspector_selected_file_ids` внутри
       этой цепочки — голова. Два таких выбора — RevisionConflict.
       «Не утв.» в этот набор не входит.
    6. Иначе голова: нет successor в пуле пригодных редакций.
    7. Голова ПД со статусом UNKNOWN — `CLARIFICATION_REQUIRED`,
       пока этот файл не выбран инспектором.
    8. Несколько голов или цикл — RevisionConflict.
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

    _reject_mixed_identities(stage_docs, stage)

    selected = [
        item for item in eligible if item.file_id in inspector_selected_file_ids
    ]
    if len(selected) > 1:
        ids = ", ".join(item.file_id for item in selected)
        raise RevisionConflict(
            f"несколько выборов инспектора для {stage.value}: {ids}"
        )
    if len(selected) == 1:
        return _finish_head(selected[0], eligible, inspector_selected=True)

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
    return _finish_head(heads[0], eligible, inspector_selected=False)


@dataclass(frozen=True, slots=True)
class IdentityHead:
    """Голова одной цепочки шифра. Конфликт чужой шифр не трогает."""

    key: tuple[str, str, str] | None
    file_ids: tuple[str, ...]
    resolution: RevisionResolution


def resolve_heads_by_identity(
    documents: list[DocumentRef],
    stage: DocStage,
    *,
    inspector_selected_file_ids: frozenset[str] = frozenset(),
) -> tuple[IdentityHead, ...]:
    """Каждый шифр стадии резолвится отдельно. Пустой шифр — своя группа."""

    stage_docs = [item for item in documents if item.doc_stage is stage]
    groups: dict[tuple[str, str, str] | None, list[DocumentRef]] = {}
    for item in stage_docs:
        groups.setdefault(_identity_key(item), []).append(item)
    result: list[IdentityHead] = []
    for key, group in groups.items():
        selected = frozenset(
            item.file_id
            for item in group
            if item.file_id in inspector_selected_file_ids
        )
        try:
            resolution = resolve_revision(
                group,
                stage,
                inspector_selected_file_ids=selected,
            )
        except RevisionConflict as exc:
            resolution = RevisionResolution(
                status=ResolveStatus.CLARIFICATION_REQUIRED,
                resolved=None,
                conflict_reason=str(exc),
            )
        result.append(
            IdentityHead(
                key=key,
                file_ids=tuple(item.file_id for item in group),
                resolution=resolution,
            )
        )
    return tuple(result)


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
