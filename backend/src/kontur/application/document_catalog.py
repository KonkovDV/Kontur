"""Список документов процесса: шифр, утверждение и актуальность головы."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from kontur.application.passport import read_passport
from kontur.application.revision_resolver import (
    ResolveStatus,
    RevisionConflict,
    approval_with_basis,
    resolve_revision,
)
from kontur.domain.models import ApprovalBasis, ApprovalStatus, DocStage, DocumentRef
from kontur.infrastructure.injection_scan import scan_tokens_for_injection
from kontur.infrastructure.pdf_guard import (
    PdfParseTimeoutError,
    pdf_parse_timeout_s,
    run_pdf_parse_sync,
)
from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes, flatten_tokens


@dataclass(frozen=True, slots=True)
class CatalogFile:
    file_id: str
    file_hash: str
    filename: str
    doc_stage: DocStage
    content: bytes


def _row(
    item: CatalogFile,
    *,
    section: str | None,
    cipher: str | None,
    revision: str | None,
    approval_status: ApprovalStatus,
    approval_basis: ApprovalBasis,
    actuality: str,
) -> dict[str, object]:
    return {
        "file_id": item.file_id,
        "filename": item.filename,
        "doc_stage": item.doc_stage.value,
        "section": section,
        "cipher": cipher,
        "revision": revision,
        "approval_status": approval_status.value,
        "approval_basis": approval_basis.value,
        "actuality": actuality,
    }


def _stamp_ref(item: CatalogFile, inspector_ids: frozenset[str]) -> tuple[DocumentRef, str | None]:
    document = run_pdf_parse_sync(
        extract_pdf_bytes,
        item.content,
        timeout_s=pdf_parse_timeout_s(),
    )
    tokens = flatten_tokens(document)
    last = document.pages[-1]
    passport = read_passport(
        tokens,
        file_id=item.file_id,
        file_hash=item.file_hash,
        filename=item.filename,
        pages=len(document.pages),
        layer_kind=document.layer_kind,
        rotate=last.frame.rotate,
        injection_clean=scan_tokens_for_injection(tokens).is_clean,
    )
    approval, basis = approval_with_basis(
        passport.approval_status,
        passport.approval_basis,
        inspector_selected=item.file_id in inspector_ids,
    )
    ref = DocumentRef(
        file_id=item.file_id,
        file_hash=item.file_hash,
        doc_stage=item.doc_stage,
        document_code=passport.document_code or "",
        revision=passport.revision or "",
        approval_status=approval,
        approval_basis=basis,
        discipline=passport.discipline,
        sheet=passport.sheet,
    )
    return ref, passport.discipline


def build_document_catalog(
    items: Sequence[CatalogFile],
    *,
    inspector_approved_file_ids: frozenset[str] = frozenset(),
) -> list[dict[str, object]]:
    """Строки для экрана комплекта. Не пишет finding_status."""

    parsed: dict[str, DocumentRef] = {}
    sections: dict[str, str | None] = {}
    failed: set[str] = set()
    for item in items:
        try:
            ref, section = _stamp_ref(item, inspector_approved_file_ids)
        except (PdfParseTimeoutError, ValueError):
            failed.add(item.file_id)
            sections[item.file_id] = None
            continue
        parsed[item.file_id] = ref
        sections[item.file_id] = section

    by_stage: dict[DocStage, list[DocumentRef]] = {stage: [] for stage in DocStage}
    for ref in parsed.values():
        by_stage[ref.doc_stage].append(ref)

    head_by_stage: dict[DocStage, DocumentRef | None] = {}
    blocked: set[DocStage] = set()
    for stage, refs in by_stage.items():
        if not refs:
            head_by_stage[stage] = None
            continue
        try:
            resolution = resolve_revision(
                refs,
                stage,
                inspector_selected_file_ids=inspector_approved_file_ids,
            )
        except RevisionConflict:
            blocked.add(stage)
            head_by_stage[stage] = None
            continue
        if resolution.status is not ResolveStatus.RESOLVED or resolution.resolved is None:
            blocked.add(stage)
            head_by_stage[stage] = None
            continue
        head_by_stage[stage] = resolution.resolved.document

    rows: list[dict[str, object]] = []
    lookup: Mapping[str, DocumentRef] = parsed
    for item in items:
        if item.file_id in failed:
            rows.append(
                _row(
                    item,
                    section=None,
                    cipher=None,
                    revision=None,
                    approval_status=ApprovalStatus.UNKNOWN,
                    approval_basis=ApprovalBasis.UNPROVEN,
                    actuality="UNREADABLE",
                )
            )
            continue
        ref = lookup[item.file_id]
        head = head_by_stage[item.doc_stage]
        if item.doc_stage in blocked or head is None:
            shown = ref
            actuality = "CLARIFICATION_REQUIRED"
        elif head.file_id == item.file_id:
            shown = head
            actuality = "CURRENT"
        else:
            shown = ref
            actuality = "SUPERSEDED"
        rows.append(
            _row(
                item,
                section=sections.get(item.file_id),
                cipher=shown.document_code or None,
                revision=shown.revision or None,
                approval_status=shown.approval_status,
                approval_basis=shown.approval_basis,
                actuality=actuality,
            )
        )
    return rows
