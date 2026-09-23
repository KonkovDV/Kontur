"""Прогон матрицы на загруженных PDF: токены → evaluate_rule → находки.

Вызывается после intake. Пустой растр при наличии Tesseract идёт в
`fill_empty_raster_pages`; иначе пустые токены. Ошибка OCR — статусы
качества, не нарушение. `ocr_text` в capabilities не становится
AVAILABLE: CA на пилоте не измерена. Автомат не пишет
CONFIRMED_VIOLATION / NEGATIVE_VERIFIED.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.passport import read_passport
from kontur.application.revision_resolver import approval_with_basis, package_etalon
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import (
    ApprovalBasis,
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceGroup,
    Finding,
)
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, FindingStatus
from kontur.infrastructure.injection_scan import scan_tokens_for_injection
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry
from kontur.infrastructure.ocr_tesseract import (
    PageImageCache,
    fill_empty_raster_pages,
    raster_pages_need_ocr,
    tesseract_available,
)
from kontur.infrastructure.pdf_guard import (
    PdfParseTimeoutError,
    pdf_parse_timeout_s,
    run_pdf_parse_sync,
)
from kontur.infrastructure.pdfium_tokens import PdfDocumentTokens, extract_pdf_bytes, flatten_tokens


@dataclass(frozen=True, slots=True)
class PipelineFile:
    file_id: str
    file_hash: str
    filename: str
    doc_stage: DocStage


@dataclass(frozen=True, slots=True)
class PipelineReport:
    findings: tuple[Finding, ...]
    rules_evaluated: int
    parse_errors: tuple[str, ...]
    pages_built: int
    stamp_by_file_id: Mapping[str, ApprovalStatus]
    evidence_groups: tuple[EvidenceGroup, ...] = ()
    injection_clean_by_file_id: Mapping[str, bool] = field(default_factory=dict)


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def _document_ref(
    item: PipelineFile,
    passport_code: str | None,
    passport_rev: str | None,
    approval: ApprovalStatus,
    basis: ApprovalBasis,
    sheet: str | None,
) -> DocumentRef:
    return DocumentRef(
        file_id=item.file_id,
        file_hash=item.file_hash,
        doc_stage=item.doc_stage,
        document_code=passport_code or "",
        revision=passport_rev or "",
        approval_status=approval,
        approval_basis=basis,
        sheet=sheet,
    )


def _pages_from_blobs(
    files: Sequence[PipelineFile],
    blobs: Mapping[str, bytes],
    *,
    inspector_approved_file_ids: frozenset[str] = frozenset(),
) -> tuple[
    dict[DocStage, StagePage],
    tuple[str, ...],
    dict[str, ApprovalStatus],
    dict[str, bool],
]:
    pages: dict[DocStage, StagePage] = {}
    errors: list[str] = []
    stamps: dict[str, ApprovalStatus] = {}
    injection_clean: dict[str, bool] = {}
    for item in files:
        if not _is_pdf(item.filename):
            continue
        raw = blobs.get(item.file_id)
        if raw is None:
            errors.append(f"{item.file_id}: нет содержимого в памяти")
            continue
        try:
            document = run_pdf_parse_sync(
                extract_pdf_bytes,
                raw,
                timeout_s=pdf_parse_timeout_s(),
            )
        except (PdfParseTimeoutError, ValueError) as exc:
            errors.append(f"{item.file_id}: {exc}")
            continue
        document = _maybe_ocr(document, raw)
        tokens = flatten_tokens(document)
        injection_clean_flag = scan_tokens_for_injection(tokens).is_clean
        last = document.pages[-1]
        passport = read_passport(
            tokens,
            file_id=item.file_id,
            file_hash=item.file_hash,
            filename=item.filename,
            pages=len(document.pages),
            layer_kind=document.layer_kind,
            rotate=last.frame.rotate,
            injection_clean=injection_clean_flag,
        )
        stamp = passport.approval_status
        stamps[item.file_id] = stamp
        injection_clean[item.file_id] = injection_clean_flag
        approval, basis = approval_with_basis(
            stamp,
            passport.approval_basis,
            inspector_selected=item.file_id in inspector_approved_file_ids,
        )
        ref = package_etalon(
            _document_ref(
                item,
                passport.document_code,
                passport.revision,
                approval,
                basis,
                passport.sheet,
            )
        )
        cache = PageImageCache(raw) if tesseract_available() else None
        pages[item.doc_stage] = StagePage(
            document=ref,
            tokens=tokens,
            pdf_bytes=raw,
            frames=tuple(page.frame for page in document.pages),
            render_cache=cache,
        )
    return pages, tuple(errors), stamps, injection_clean


def run_process_pipeline(
    *,
    object_id: str,
    completeness: CompletenessMap,
    files: Sequence[PipelineFile],
    blobs: Mapping[str, bytes],
    registry: FileRuleRegistry | None = None,
    inspector_approved_file_ids: frozenset[str] = frozenset(),
) -> PipelineReport:
    """Исполнить все строки матрицы. Пустые страницы → статусы качества, не violation."""

    source = registry or FileRuleRegistry()
    codes = source.all_codes()
    if len(codes) != EXPECTED_PARAM_COUNT:
        raise ValueError(f"матрица {len(codes)} правил, ожидалось {EXPECTED_PARAM_COUNT}")
    pages, parse_errors, stamps, injection_clean = _pages_from_blobs(
        files,
        blobs,
        inspector_approved_file_ids=inspector_approved_file_ids,
    )
    findings: list[Finding] = []
    groups: list[EvidenceGroup] = []
    for code in codes:
        result = evaluate_rule(
            source.get(code),
            object_id=object_id,
            pages=pages,
            completeness=completeness,
        )
        finding = result.finding
        if finding.finding_status in HUMAN_ONLY_STATUSES:
            raise RuntimeError(f"{code}: автомат записал {finding.finding_status.value}")
        findings.append(replace(finding, finding_id=f"pipe-{code}"))
        if result.evidence_group is not None:
            groups.append(result.evidence_group)
    report = PipelineReport(
        findings=tuple(findings),
        rules_evaluated=len(findings),
        parse_errors=parse_errors,
        pages_built=len(pages),
        stamp_by_file_id=stamps,
        evidence_groups=tuple(groups),
        injection_clean_by_file_id=injection_clean,
    )
    assert_machine_only(report.findings)
    return report


def fill_raster_pages_isolated(data: bytes) -> PdfDocumentTokens:
    """OCR-fill в дочернем процессе: pickle без замыкания на исходный документ."""

    return fill_empty_raster_pages(extract_pdf_bytes(data), data)


def _maybe_ocr(document: PdfDocumentTokens, raw: bytes) -> PdfDocumentTokens:
    """OCR вне векторного разбора. Таймаут оставляет исходные токены."""

    if not tesseract_available() or not raster_pages_need_ocr(document):
        return document
    try:
        return run_pdf_parse_sync(fill_raster_pages_isolated, raw)
    except PdfParseTimeoutError:
        return document


def stamp_approval_from_pdf(
    data: bytes,
    *,
    file_id: str,
    file_hash: str,
    filename: str,
) -> ApprovalStatus:
    """Прочитать штамп без overlay инспектора. Таймаут → UNKNOWN, не APPROVED."""

    try:
        document = run_pdf_parse_sync(extract_pdf_bytes, data)
    except (PdfParseTimeoutError, ValueError):
        return ApprovalStatus.UNKNOWN
    tokens = flatten_tokens(document)
    last = document.pages[-1]
    passport = read_passport(
        tokens,
        file_id=file_id,
        file_hash=file_hash,
        filename=filename,
        pages=len(document.pages),
        layer_kind=document.layer_kind,
        rotate=last.frame.rotate,
    )
    return passport.approval_status


def assert_machine_only(findings: Sequence[Finding]) -> None:
    """Сторож: пайплайн не имеет права закрыть очередь инспектора."""

    for finding in findings:
        if finding.finding_status in HUMAN_ONLY_STATUSES:
            raise RuntimeError(f"{finding.rule_code}: {finding.finding_status.value}")
        if finding.finding_status is FindingStatus.CONFIRMED_VIOLATION:
            raise RuntimeError("CONFIRMED_VIOLATION из пайплайна")
