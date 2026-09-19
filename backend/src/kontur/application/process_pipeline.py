"""Прогон матрицы на загруженных PDF: токены → evaluate_rule → находки.

Гейт I (24.09): страницы без текстового слоя направляются в OCR-верификатор
(Tesseract-5 region-crop ×3). Токены verifierа заменяют пустой вектор.
Если Tesseract недоступен: пустые токены → статусы качества, не violation.
Автомат не пишет CONFIRMED_VIOLATION / NEGATIVE_VERIFIED.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.passport import read_passport
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef, Finding
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, FindingStatus
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry
from kontur.infrastructure.ocr_verifier import ocr_document_raster_pages
from kontur.infrastructure.pdf_guard import PdfParseTimeoutError, run_pdf_parse_sync
from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes, flatten_tokens


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


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def _document_ref(
    item: PipelineFile,
    passport_code: str | None,
    passport_rev: str | None,
    approval: ApprovalStatus,
    sheet: str | None,
) -> DocumentRef:
    return DocumentRef(
        file_id=item.file_id,
        file_hash=item.file_hash,
        doc_stage=item.doc_stage,
        document_code=passport_code or "",
        revision=passport_rev or "",
        approval_status=approval,
        sheet=sheet,
    )


def _augment_with_ocr(
    raw: bytes,
    document,  # PdfDocumentTokens
) -> tuple:
    """Дополнить токены OCR для растровых страниц (Gate I).

    Векторные страницы: токены уже есть — OCR не запускается.
    Растровые страницы: пустые токены заменяются на OCR-токены.
    Если Tesseract недоступен — возвращаем пустые токены как есть.
    """
    ocr_by_page = ocr_document_raster_pages(raw, document.pages)
    if not ocr_by_page:
        return flatten_tokens(document)
    result: list = []
    for page in document.pages:
        if page.has_embedded_text:
            result.extend(page.tokens)
        else:
            ocr_result = ocr_by_page.get(page.page)
            if ocr_result is not None:
                result.extend(ocr_result.tokens)
    return tuple(result)


def _pages_from_blobs(
    files: Sequence[PipelineFile],
    blobs: Mapping[str, bytes],
) -> tuple[dict[DocStage, StagePage], tuple[str, ...]]:
    pages: dict[DocStage, StagePage] = {}
    errors: list[str] = []
    for item in files:
        if not _is_pdf(item.filename):
            continue
        raw = blobs.get(item.file_id)
        if raw is None:
            errors.append(f"{item.file_id}: нет содержимого в памяти")
            continue
        try:
            document = run_pdf_parse_sync(extract_pdf_bytes, raw)
        except (PdfParseTimeoutError, ValueError) as exc:
            errors.append(f"{item.file_id}: {exc}")
            continue
        # Gate I: растровые страницы → OCR-токены (fallback: пустой вектор)
        tokens = _augment_with_ocr(raw, document)
        last = document.pages[-1]
        passport = read_passport(
            tokens,
            file_id=item.file_id,
            file_hash=item.file_hash,
            filename=item.filename,
            pages=len(document.pages),
            layer_kind=document.layer_kind,
            rotate=last.frame.rotate,
        )
        ref = _document_ref(
            item,
            passport.document_code,
            passport.revision,
            passport.approval_status,
            passport.sheet,
        )
        pages[item.doc_stage] = StagePage(document=ref, tokens=tokens)
    return pages, tuple(errors)


def run_process_pipeline(
    *,
    object_id: str,
    completeness: CompletenessMap,
    files: Sequence[PipelineFile],
    blobs: Mapping[str, bytes],
    registry: FileRuleRegistry | None = None,
) -> PipelineReport:
    """Исполнить все строки матрицы. Пустые страницы → статусы качества, не violation."""

    source = registry or FileRuleRegistry()
    codes = source.all_codes()
    if len(codes) != EXPECTED_PARAM_COUNT:
        raise ValueError(f"матрица {len(codes)} правил, ожидалось {EXPECTED_PARAM_COUNT}")
    pages, parse_errors = _pages_from_blobs(files, blobs)
    findings: list[Finding] = []
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
    report = PipelineReport(
        findings=tuple(findings),
        rules_evaluated=len(findings),
        parse_errors=parse_errors,
        pages_built=len(pages),
    )
    assert_machine_only(report.findings)
    return report


def assert_machine_only(findings: Sequence[Finding]) -> None:
    """Сторож: пайплайн не имеет права закрыть очередь инспектора."""

    for finding in findings:
        if finding.finding_status in HUMAN_ONLY_STATUSES:
            raise RuntimeError(f"{finding.rule_code}: {finding.finding_status.value}")
        if finding.finding_status is FindingStatus.CONFIRMED_VIOLATION:
            raise RuntimeError("из пайплайна CONFIRMED_VIOLATION")
