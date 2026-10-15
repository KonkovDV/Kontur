"""Прогон матрицы на загруженных PDF: токены → голова редакции → evaluate_rule.

Несколько файлов одной стадии без successor не схлопываются в последний
файл. Разные шифры — отдельные головы. Нет однозначной головы шифра —
эта цепочка в страницы стадии не входит.

Вызывается после intake. Пустой растр при наличии Tesseract идёт в
`fill_empty_raster_pages`; иначе пустые токены. Ошибка OCR — статусы
качества, не нарушение. XML отдаёт текстовые узлы, zip — PDF, DOCX и XML
из архива. 7z и rar не распаковываются. `ocr_text` в capabilities не
становится AVAILABLE: CA на пилоте не измерена. Автомат не пишет
CONFIRMED_VIOLATION / NEGATIVE_VERIFIED.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from time import perf_counter

from kontur.application.archive_expand import expand_zip
from kontur.application.docx_text import DocxReadError, read_docx_bytes
from kontur.application.evaluate import StagePage, evaluate_free_search, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.passport import apply_manifest_section, read_passport
from kontur.application.revision_resolver import (
    ResolveStatus,
    _identity_key,
    approval_with_basis,
    resolve_heads_by_identity,
)
from kontur.application.scenarios import CompletenessMap
from kontur.application.xml_text import XmlReadError, read_xml_bytes
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
from kontur.infrastructure.matrix.free_search import load_free_search
from kontur.infrastructure.matrix.registry import (
    EXPECTED_PARAM_COUNT,
    FileRuleRegistry,
    discover_matrix_root,
)
from kontur.infrastructure.ocr_tesseract import (
    PageImageCache,
    fill_empty_raster_pages,
    raster_pages_need_ocr,
    stamp_cipher_reads,
    tesseract_available,
)
from kontur.infrastructure.pdf_guard import (
    PdfParseTimeoutError,
    pdf_parse_timeout_s,
    run_pdf_parse_sync,
)
from kontur.infrastructure.pdfium_tokens import (
    PdfDocumentTokens,
    extract_pdf_bytes,
    file_sha256,
    flatten_tokens,
)


@dataclass(frozen=True, slots=True)
class PipelineFile:
    file_id: str
    file_hash: str
    filename: str
    doc_stage: DocStage
    predecessor_file_id: str | None = None
    successor_file_id: str | None = None
    manifest_section: str | None = None
    manifest_path: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineReport:
    findings: tuple[Finding, ...]
    rules_evaluated: int
    parse_errors: tuple[str, ...]
    pages_built: int
    stamp_by_file_id: Mapping[str, ApprovalStatus]
    evidence_groups: tuple[EvidenceGroup, ...] = ()
    injection_clean_by_file_id: Mapping[str, bool] = field(default_factory=dict)
    #: Монотонные секунды разбора и сравнения. Загрузка и экспорт протокола
    #: в этот отчёт не входят: их часы живут у вызывающего.
    phase_seconds: Mapping[str, float] = field(default_factory=dict)
    #: Документы, достатые из zip. Их байты нужно положить к комплекту,
    #: иначе карточка доказательства не найдёт страницу.
    expanded_files: tuple[PipelineFile, ...] = ()
    expanded_blobs: Mapping[str, bytes] = field(default_factory=dict)


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def _archive_suffix(filename: str) -> str | None:
    """Архив — способ поставки, не формат сверки."""

    lower = filename.lower()
    for suffix in (".zip", ".7z", ".rar"):
        if lower.endswith(suffix):
            return suffix
    return None


def _office_suffix(filename: str) -> str | None:
    """DOCX и XML разбираются текстом. Схема XML не интерпретируется."""

    lower = filename.lower()
    for suffix in (".docx", ".xml"):
        if lower.endswith(suffix):
            return suffix
    return None


def _document_ref(
    item: PipelineFile,
    passport_code: str | None,
    passport_rev: str | None,
    approval: ApprovalStatus,
    basis: ApprovalBasis,
    sheet: str | None,
    discipline: str | None = None,
    revision_kind: str = "",
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
        discipline=discipline,
        predecessor_file_id=item.predecessor_file_id,
        successor_file_id=item.successor_file_id,
        source_name=item.filename,
        revision_kind=revision_kind,
    )


def _append_text_page(
    item: PipelineFile,
    tokens: tuple[PageToken, ...],
    *,
    inspector_approved_file_ids: frozenset[str],
    stamps: dict[str, ApprovalStatus],
    injection_clean: dict[str, bool],
    built: list[tuple[DocumentRef, StagePage]],
) -> None:
    """Паспорт и голова для текста DOCX или XML. Страница одна."""

    injection_clean_flag = scan_tokens_for_injection(tokens).is_clean
    passport = read_passport(
        tokens,
        file_id=item.file_id,
        file_hash=item.file_hash,
        filename=item.filename,
        pages=1,
        layer_kind="vector",
        injection_clean=injection_clean_flag,
    )
    passport = apply_manifest_section(
        passport,
        section=item.manifest_section,
        relative_path=item.manifest_path,
        filename=item.filename,
    )
    stamp = passport.approval_status
    stamps[item.file_id] = stamp
    injection_clean[item.file_id] = injection_clean_flag
    approval, basis = approval_with_basis(
        stamp,
        passport.approval_basis,
        inspector_selected=item.file_id in inspector_approved_file_ids,
    )
    ref = _document_ref(
        item,
        passport.identity_code,
        passport.revision,
        approval,
        basis,
        passport.sheet,
        passport.discipline,
        passport.revision_kind,
    )
    built.append((ref, StagePage(document=ref, tokens=tokens)))


def _pages_from_blobs(
    files: Sequence[PipelineFile],
    blobs: Mapping[str, bytes],
    *,
    inspector_approved_file_ids: frozenset[str] = frozenset(),
    expanded_out: list[PipelineFile] | None = None,
    expanded_blobs: dict[str, bytes] | None = None,
) -> tuple[
    dict[DocStage, StagePage | tuple[StagePage, ...]],
    tuple[str, ...],
    dict[str, ApprovalStatus],
    dict[str, bool],
    list[DocumentRef],
]:
    """Страница стадии — голова резолвера, не последний загруженный файл.

    Нет однозначной головы — страницы стадии нет. Штамп в `stamps` остаётся
    прочитанным, без `PACKAGE_DEFAULT`.
    """

    errors: list[str] = []
    stamps: dict[str, ApprovalStatus] = {}
    injection_clean: dict[str, bool] = {}
    built: list[tuple[DocumentRef, StagePage]] = []
    pending = list(files)
    stored = dict(blobs)
    seen: set[str] = set()
    while pending:
        item = pending.pop(0)
        if item.file_id in seen:
            errors.append(f"{item.file_id}: повтор file_id")
            continue
        seen.add(item.file_id)
        office = _office_suffix(item.filename)
        if office == ".xml":
            raw = stored.get(item.file_id)
            if raw is None:
                errors.append(f"{item.file_id}: нет содержимого в памяти")
                continue
            try:
                parsed_xml = read_xml_bytes(raw)
            except XmlReadError as exc:
                errors.append(f"{item.file_id}: {exc}")
                continue
            if not parsed_xml.tokens:
                errors.append(f"{item.file_id}: XML: текст не прочитан")
                continue
            _append_text_page(
                item,
                parsed_xml.tokens,
                inspector_approved_file_ids=inspector_approved_file_ids,
                stamps=stamps,
                injection_clean=injection_clean,
                built=built,
            )
            continue
        if office == ".docx":
            raw = stored.get(item.file_id)
            if raw is None:
                errors.append(f"{item.file_id}: нет содержимого в памяти")
                continue
            try:
                parsed = read_docx_bytes(raw)
            except DocxReadError as exc:
                errors.append(f"{item.file_id}: {exc}")
                continue
            if not parsed.tokens:
                errors.append(f"{item.file_id}: DOCX: текст не прочитан")
                continue
            if parsed.skipped:
                skipped = ", ".join(parsed.skipped)
                errors.append(f"{item.file_id}: DOCX: пропущены {skipped}")
            _append_text_page(
                item,
                parsed.tokens,
                inspector_approved_file_ids=inspector_approved_file_ids,
                stamps=stamps,
                injection_clean=injection_clean,
                built=built,
            )
            continue
        archive = _archive_suffix(item.filename)
        if archive == ".zip":
            raw = stored.get(item.file_id)
            if raw is None:
                errors.append(f"{item.file_id}: нет содержимого в памяти")
                continue
            try:
                members = expand_zip(item.file_id, raw)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            for index, (filename, content) in enumerate(members, start=1):
                child = PipelineFile(
                    file_id=f"{item.file_id}__{index}",
                    file_hash=file_sha256(content),
                    filename=filename,
                    doc_stage=item.doc_stage,
                    manifest_section=item.manifest_section,
                    manifest_path=item.manifest_path,
                )
                stored[child.file_id] = content
                pending.append(child)
                if expanded_out is not None:
                    expanded_out.append(child)
                if expanded_blobs is not None:
                    expanded_blobs[child.file_id] = content
            continue
        if archive is not None:
            errors.append(
                f"{item.file_id}: ARCHIVE_NOT_EXPANDED: {archive} распакуйте до сверки"
            )
            continue
        if not _is_pdf(item.filename):
            dot = item.filename.rfind(".")
            suffix = item.filename[dot:].lower() if dot >= 0 else ""
            label = suffix or ".нет"
            errors.append(
                f"{item.file_id}: UNSUPPORTED_FORMAT: {label} не входит в разбор PDF"
            )
            continue
        raw = stored.get(item.file_id)
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
            alternate_ciphers=stamp_cipher_reads(raw, len(document.pages)),
        )
        passport = apply_manifest_section(
            passport,
            section=item.manifest_section,
            relative_path=item.manifest_path,
            filename=item.filename,
        )
        stamp = passport.approval_status
        stamps[item.file_id] = stamp
        injection_clean[item.file_id] = injection_clean_flag
        approval, basis = approval_with_basis(
            stamp,
            passport.approval_basis,
            inspector_selected=item.file_id in inspector_approved_file_ids,
        )
        ref = _document_ref(
            item,
            passport.identity_code,
            passport.revision,
            approval,
            basis,
            passport.sheet,
            passport.discipline,
            passport.revision_kind,
        )
        cache = PageImageCache(raw) if tesseract_available() else None
        built.append(
            (
                ref,
                StagePage(
                    document=ref,
                    tokens=tokens,
                    pdf_bytes=raw,
                    frames=tuple(page.frame for page in document.pages),
                    render_cache=cache,
                ),
            )
        )
    pool = [ref for ref, _page in built]
    pages = _stages_from_heads(built, inspector_approved_file_ids)
    return pages, tuple(errors), stamps, injection_clean, pool


def _stages_from_heads(
    built: Sequence[tuple[DocumentRef, StagePage]],
    inspector_approved_file_ids: frozenset[str],
) -> dict[DocStage, StagePage | tuple[StagePage, ...]]:
    """Одна или несколько голов стадии: по шифру, не последний файл."""

    by_stage: dict[DocStage, list[tuple[DocumentRef, StagePage]]] = {}
    for ref, page in built:
        by_stage.setdefault(ref.doc_stage, []).append((ref, page))
    pages: dict[DocStage, StagePage | tuple[StagePage, ...]] = {}
    for stage, items in by_stage.items():
        refs = [ref for ref, _page in items]
        by_id = {ref.file_id: page for ref, page in items}
        heads: list[StagePage] = []
        for identity in resolve_heads_by_identity(
            refs,
            stage,
            inspector_selected_file_ids=inspector_approved_file_ids,
        ):
            if (
                identity.resolution.status is not ResolveStatus.RESOLVED
                or identity.resolution.resolved is None
            ):
                continue
            chosen = identity.resolution.resolved.document
            heads.append(replace(by_id[chosen.file_id], document=chosen))
        if stage is DocStage.PD and inspector_approved_file_ids:
            heads = [
                page
                for page in heads
                if page.document.file_id in inspector_approved_file_ids
                or _identity_key(page.document) is not None
            ]
        if len(heads) == 1:
            pages[stage] = heads[0]
        elif len(heads) > 1:
            pages[stage] = tuple(heads)
    return pages


def _count_built_pages(
    pages: Mapping[DocStage, StagePage | tuple[StagePage, ...]],
) -> int:
    total = 0
    for item in pages.values():
        total += len(item) if isinstance(item, tuple) else 1
    return total


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
    parse_started = perf_counter()
    expanded_files: list[PipelineFile] = []
    expanded_blobs: dict[str, bytes] = {}
    pages, parse_errors, stamps, injection_clean, revision_pool = _pages_from_blobs(
        files,
        blobs,
        inspector_approved_file_ids=inspector_approved_file_ids,
        expanded_out=expanded_files,
        expanded_blobs=expanded_blobs,
    )
    parse_seconds = perf_counter() - parse_started
    compare_started = perf_counter()
    findings: list[Finding] = []
    groups: list[EvidenceGroup] = []
    for code in codes:
        result = evaluate_rule(
            source.get(code),
            object_id=object_id,
            pages=pages,
            completeness=completeness,
            revision_pool=revision_pool,
            inspector_selected_file_ids=inspector_approved_file_ids,
        )
        batch = (result, *result.also)
        for index, item in enumerate(batch):
            finding = item.finding
            if finding.finding_status in HUMAN_ONLY_STATUSES:
                raise RuntimeError(f"{code}: автомат записал {finding.finding_status.value}")
            suffix = "" if index == 0 else f"-{index}"
            findings.append(replace(finding, finding_id=f"pipe-{code}{suffix}"))
            if item.evidence_group is not None:
                groups.append(item.evidence_group)
    catalog = discover_matrix_root() / "free_search.json"
    if catalog.is_file():
        for entry in load_free_search(catalog):
            if entry.room_compare is None:
                continue
            searched = evaluate_free_search(
                {
                    "code": entry.parameter_code,
                    "matrix_version": source.matrix_version,
                    "extractor": {
                        "type": "room_compare",
                        "room_compare": entry.room_compare,
                        "provision": entry.provision,
                    },
                },
                pages,
                object_id,
            )
            for index, item in enumerate(searched):
                finding = item.finding
                if finding.finding_status is not FindingStatus.SUSPICION:
                    raise RuntimeError(
                        f"{entry.parameter_code}: свободный поиск записал "
                        f"{finding.finding_status.value}"
                    )
                suffix = "" if index == 0 else f"-{index}"
                findings.append(
                    replace(finding, finding_id=f"pipe-{entry.parameter_code}{suffix}")
                )
                if item.evidence_group is not None:
                    groups.append(item.evidence_group)
    compare_seconds = perf_counter() - compare_started
    report = PipelineReport(
        findings=tuple(findings),
        rules_evaluated=len(codes),
        parse_errors=parse_errors,
        pages_built=_count_built_pages(pages),
        stamp_by_file_id=stamps,
        evidence_groups=tuple(groups),
        injection_clean_by_file_id=injection_clean,
        phase_seconds={"parse": parse_seconds, "compare": compare_seconds},
        expanded_files=tuple(expanded_files),
        expanded_blobs=expanded_blobs,
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
