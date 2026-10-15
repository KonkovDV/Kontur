"""Резолвер актуальной редакции (Gate E, ТЗ п. 9.1, ответ организатора 26.09).

ПД без штампа: `KONTUR_ETALON_POLICY=strict` даёт `CLARIFICATION_REQUIRED`.
`sole_head` (по умолчанию) берёт единственную голову без другой утверждённой
редакции в цепочке и ставит `SOLE_HEAD`, не переписывая штамп в APPROVED.
РД и ИД не требуют графы «Утвердил». `NOT_APPROVED` в пул не входит.
Несколько голов или цикл — `CLARIFICATION_REQUIRED`, без сравнения.

Резолвер не пишет `finding_status` сравнения: успешный выбор эталона — это
не «расхождения нет».
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from enum import StrEnum

from kontur.domain.models import ApprovalBasis, ApprovalStatus, DocStage, DocumentRef

SOLE_HEAD_NOTICE = "утверждение не подтверждено"

_COPY_SUFFIX = re.compile(r"\s*\(\d{1,2}\)\s*$")
_FILENAME_MARK = re.compile(
    r"(?:^|[\s._\-])(изм|корр?|ред)(?:[\s._\-]*(\d{1,2}))?(?!\d)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _NameMark:
    kind: str
    number: int | None


def _volume_key(source_name: str) -> str:
    """Шифр из имени без «кор3», «изм. 2» и «(1)». Пустое имя группу не создаёт."""

    stem = source_name.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    stem = _COPY_SUFFIX.sub("", stem)
    stem = _FILENAME_MARK.sub(" ", stem)
    return re.sub(r"[^0-9a-zа-яё]", "", stem.casefold())


def _name_mark(doc: DocumentRef) -> _NameMark:
    """Номер с титула важнее имени. «Изм» и «кор» в одном имени не складываются."""

    if doc.revision.strip().isdigit():
        kind = doc.revision_kind if doc.revision_kind in {"change", "correction"} else "correction"
        return _NameMark(kind, int(doc.revision.strip()))
    stem = _COPY_SUFFIX.sub(
        "",
        doc.source_name.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0],
    )
    found = _FILENAME_MARK.findall(stem)
    kinds = {item[0].casefold()[:3] for item in found}
    folded = set()
    for kind in kinds:
        folded.add("change" if kind.startswith("изм") else "correction")
    if len(folded) > 1:
        return _NameMark("mixed", None)
    number = next((int(item[1]) for item in found if item[1]), None)
    if not folded:
        return _NameMark("none", 0 if doc.source_name.strip() else None)
    kind = next(iter(folded))
    return _NameMark(kind, number)


def _chain_by_filename(
    group: list[DocumentRef],
) -> tuple[list[DocumentRef], str | None]:
    """Одна цепочка имени. Разные шкалы и один номер у разных файлов — уточнение."""

    marks = [_name_mark(item) for item in group]
    if any(item.kind == "mixed" for item in marks):
        return group, "в имени смешаны изм и кор, порядок редакции не выбирается"
    kinds = {item.kind for item in marks}
    if "change" in kinds and ({"correction", "stamp"} & kinds):
        return group, "изм и кор не упорядочиваются между собой"
    by_number: dict[int, DocumentRef] = {}
    for doc, mark in zip(group, marks, strict=True):
        if mark.number is None:
            return group, "номер редакции в имени не прочитан"
        previous = by_number.get(mark.number)
        if previous is not None and previous.file_hash != doc.file_hash:
            return group, "один номер редакции у разных файлов"
        by_number[mark.number] = doc
    ordered = [by_number[number] for number in sorted(by_number)]
    linked: list[DocumentRef] = []
    for index, doc in enumerate(ordered):
        predecessor = ordered[index - 1].file_id if index else None
        successor = ordered[index + 1].file_id if index + 1 < len(ordered) else None
        linked.append(
            replace(
                doc,
                predecessor_file_id=predecessor,
                successor_file_id=successor,
            )
        )
    return linked, None


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


def etalon_policy() -> str:
    """`sole_head` по умолчанию. Неизвестное значение — `strict`, как ADR-0015."""

    raw = os.environ.get("KONTUR_ETALON_POLICY", "sole_head").strip().lower()
    if raw == "sole_head":
        return "sole_head"
    return "strict"


def _eligible(doc: DocumentRef) -> bool:
    """В пул головы входит всё, кроме явного «не утв.»."""

    return doc.approval_status is not ApprovalStatus.NOT_APPROVED


def _finish_head(
    chosen: DocumentRef,
    eligible: list[DocumentRef],
    *,
    inspector_selected: bool,
) -> RevisionResolution:
    """ПД без штампа: strict останавливает, sole_head берёт единственную голову.

    Выбор инспектора переводит UNKNOWN в APPROVED с INSPECTOR_SELECT.
    Явный «не утв.» в эту функцию не приходит. РД и ИД сравнение не останавливают.
    Другая утверждённая редакция той же цепочки не даёт назначить черновик эталоном.
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
        approved_other = any(
            item.file_id != chosen.file_id and item.approval_status is ApprovalStatus.APPROVED
            for item in eligible
        )
        if etalon_policy() == "sole_head" and not approved_other:
            chosen = replace(chosen, approval_basis=ApprovalBasis.SOLE_HEAD)
        else:
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
    2. При `anchor` — только тот же `_identity_key`. Пустой шифр якоря
       берёт свой компонент файлов без шифра и не захватывает тома с шифром.
    3. `NOT_APPROVED` в пул голов не попадает. ПД без штампа остаётся кандидатом.
    4. Разные шифры или лист/раздел — не одна цепочка. Выбор инспектора
       чужой документ не поглощает.
    5. Ровно один пригодный файл из `inspector_selected_file_ids` внутри
       этой цепочки — голова. Два таких выбора — RevisionConflict.
       «Не утв.» в этот набор не входит.
    6. Иначе голова: нет successor в пуле пригодных редакций.
    7. Голова ПД со статусом UNKNOWN. Выбор инспектора ставит APPROVED.
       Иначе `strict` — `CLARIFICATION_REQUIRED`. `sole_head` берёт эту
       голову с SOLE_HEAD, если в цепочке нет другой APPROVED редакции.
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
        anchor_key = _identity_key(anchor)
        if anchor_key is not None:
            stage_docs = [item for item in stage_docs if _identity_key(item) == anchor_key]
        else:
            blanks = [item for item in stage_docs if _identity_key(item) is None]
            stage_docs = next(
                (
                    component
                    for component in _blank_components(blanks)
                    if any(item.file_id == anchor.file_id for item in component)
                ),
                [],
            )
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
    """Каждый шифр стадии резолвится отдельно.

    Пустой шифр без связи predecessor/successor — своя группа.
    Явный successor между пустыми шифрами держит их одной цепочкой.
    """

    stage_docs = [item for item in documents if item.doc_stage is stage]
    groups: dict[tuple[str, str, str], list[DocumentRef]] = {}
    blanks: list[DocumentRef] = []
    for item in stage_docs:
        key = _identity_key(item)
        if key is None:
            blanks.append(item)
            continue
        groups.setdefault(key, []).append(item)
    result: list[IdentityHead] = []
    keyed: list[tuple[tuple[str, str, str] | None, list[DocumentRef]]] = [
        (key, group) for key, group in groups.items()
    ]
    keyed.extend(
        (None, component) for component in _blank_filename_groups(blanks, stage)
    )
    for key, group in keyed:
        selected = frozenset(
            item.file_id
            for item in group
            if item.file_id in inspector_selected_file_ids
        )
        filename_conflict = _filename_group_conflict(group, stage)
        try:
            if filename_conflict is not None:
                raise RevisionConflict(filename_conflict)
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


def _blank_filename_groups(
    blanks: list[DocumentRef],
    stage: DocStage,
) -> list[list[DocumentRef]]:
    """ПД и РД с пустым шифром: одно имя без метки редакции — одна цепочка.

    ИД не схлопывается: акты не заменяют друг друга. Связь predecessor
    остаётся сильнее имени.
    """

    components = _blank_components(blanks)
    if stage is DocStage.ID:
        return components
    kept: list[list[DocumentRef]] = []
    loose: list[DocumentRef] = []
    for component in components:
        if len(component) == 1 and component[0].source_name.strip():
            loose.append(component[0])
        else:
            kept.append(component)
    clusters: dict[str, list[DocumentRef]] = {}
    for doc in loose:
        key = _volume_key(doc.source_name)
        if not key:
            kept.append([doc])
            continue
        clusters.setdefault(key, []).append(doc)
    for group in clusters.values():
        if len(group) == 1:
            kept.append(group)
            continue
        linked, conflict = _chain_by_filename(group)
        if conflict is not None:
            kept.append(group)
            continue
        kept.append(linked)
    return kept


def _filename_group_conflict(group: list[DocumentRef], stage: DocStage) -> str | None:
    if stage is DocStage.ID or len(group) < 2:
        return None
    if any(not item.source_name.strip() for item in group):
        return None
    keys = {_volume_key(item.source_name) for item in group}
    if len(keys) != 1 or not next(iter(keys)):
        return None
    if any(item.predecessor_file_id or item.successor_file_id for item in group):
        return None
    _linked, conflict = _chain_by_filename(group)
    return conflict


def _blank_components(blanks: list[DocumentRef]) -> list[list[DocumentRef]]:
    """Связанные пустые шифры — один компонент, остальные — по файлу."""

    parent = {item.file_id: item.file_id for item in blanks}

    def find(file_id: str) -> str:
        while parent[file_id] != file_id:
            parent[file_id] = parent[parent[file_id]]
            file_id = parent[file_id]
        return file_id

    def union(left: str, right: str | None) -> None:
        if right is None or right not in parent:
            return
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for item in blanks:
        union(item.file_id, item.predecessor_file_id)
        union(item.file_id, item.successor_file_id)
    components: dict[str, list[DocumentRef]] = {}
    for item in blanks:
        components.setdefault(find(item.file_id), []).append(item)
    return list(components.values())


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
