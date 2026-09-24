"""FastAPI-фасад с RBAC и fail-closed object scope для каждого процесса."""

from __future__ import annotations

import os
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from kontur.application.document_catalog import CatalogFile, build_document_catalog
from kontur.application.evidence_card import build_evidence_card
from kontur.application.intake import (
    MAX_BATCH_BYTES,
    Rejection,
    UploadCandidate,
    evaluate_batch,
)
from kontur.application.protocol import assemble_protocol, protocol_for_http
from kontur.application.protocol_export import (
    ProtocolPdfUnavailable,
    render_docx,
    render_pdf,
    render_xml,
)
from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.capabilities import capabilities_payload
from kontur.domain.models import DocStage, Finding
from kontur.domain.state_machines import TransitionError
from kontur.domain.status_map import EmptyPackageError, protocol_status
from kontur.domain.statuses import Completeness, ProcessState, ReasonCode
from kontur.evaluation.demo_kit import DRAFT_FILE_ID, ETALON_FILE_ID, install_demo_kit
from kontur.infrastructure.access_control import AccessDeniedError, check_object_access
from kontur.infrastructure.db.process_store import (
    ProtocolConflictError,
    ProtocolMaterializationRequiredError,
    TransactionUnavailableError,
)
from kontur.infrastructure.matrix.registry import FileRuleRegistry
from kontur.infrastructure.pdfium_page import PageRenderError, parse_bbox, render_page_png
from kontur.presentation.auth import _is_true, actor_from_roles, parse_bearer
from kontur.presentation.rbac import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    Role,
    authorize,
)
from kontur.presentation.upload_limits import (
    ActualUploadLimitMiddleware,
    read_bounded_upload,
)

app = FastAPI(title="Инспектор ИИ", version="0.1.0-skeleton")
app.add_middleware(ActualUploadLimitMiddleware)
app.state.workspace = ProcessWorkspace()


class FinalizeRequest(BaseModel):
    inspector_id: str = Field(min_length=1)


class UnfinalizeRequest(BaseModel):
    inspector_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReviewRequest(BaseModel):
    action: str = Field(min_length=1)
    inspector_id: str = Field(min_length=1)
    comment: str = Field(min_length=1)
    reason_code: ReasonCode | None = None


class SelectRevisionRequest(BaseModel):
    inspector_id: str = Field(min_length=1)
    comment: str = Field(min_length=1)


def _rules() -> FileRuleRegistry:
    registry = getattr(app.state, "rules", None)
    if not isinstance(registry, FileRuleRegistry):
        registry = FileRuleRegistry()
        app.state.rules = registry
    return registry


def _finding_on_record(record: ProcessRecord, finding_id: str) -> Finding | None:
    for key, item in record.findings.items():
        if item.finding_id == finding_id or key == finding_id:
            return item
    return None


def _workspace() -> ProcessWorkspace:
    store = getattr(app.state, "workspace", None)
    if store is None:
        store = ProcessWorkspace()
        app.state.workspace = store
    return store


def _empty_completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _require(
    operation_id: str,
    authorization: str | None,
) -> tuple[str, frozenset[Role], str | None]:
    context = parse_bearer(authorization)
    granted = authorize(operation_id, context.roles)
    return context.subject, granted, context.object_id


def _check_scope(requested_object_id: str, caller_object_id: str | None) -> None:
    check_object_access(
        requested_object_id=requested_object_id,
        caller_object_id=caller_object_id,
    )


def _record_for_access(
    process_id: str,
    caller_object_id: str | None,
) -> ProcessRecord | None:
    record = _workspace().get(process_id)
    if record is None:
        return None
    _check_scope(record.object_id, caller_object_id)
    return record


def _record_for_finding(finding_id: str) -> ProcessRecord | None:
    """Найти уже загруженный процесс так же, как текущий workspace.review_finding."""

    workspace = _workspace()
    for record in workspace._items.values():  # noqa: SLF001 - единая in-memory граница
        for key, item in record.findings.items():
            if item.finding_id == finding_id or key == finding_id:
                return record
    return None


def _rejection_body(item: Rejection) -> dict[str, str]:
    return {
        "file_name": item.filename,
        "reason_code": item.reason.value,
        "message": item.detail,
    }


def _attach_new_files(
    workspace: ProcessWorkspace,
    record: ProcessRecord,
    accepted_items: tuple[UploadCandidate, ...],
    bodies: dict[str, bytes],
    doc_stage: DocStage,
) -> list[dict[str, str]]:
    attached: list[dict[str, str]] = []
    for item in accepted_items:
        digest = item.content_hash
        if digest is None:
            raise RuntimeError("принятый файл обязан иметь SHA-256")
        stored = AcceptedFile(
            file_id=str(uuid4()),
            file_hash=digest,
            filename=item.filename,
            doc_stage=doc_stage,
            size_bytes=item.size_bytes,
        )
        if workspace.attach_file(record, stored):
            workspace.keep_blob(record, stored.file_id, bodies[digest])
            attached.append({"file_id": stored.file_id, "file_hash": stored.file_hash})
    return attached


def _upload_receipt(
    record: ProcessRecord,
    attached: list[dict[str, str]],
    rejected: tuple[Rejection, ...],
) -> dict[str, object]:
    return {
        "process_id": record.process_id,
        "accepted": attached,
        "rejected": [_rejection_body(item) for item in rejected],
    }


@app.exception_handler(TransitionError)
async def _transition_error(_request: object, exc: TransitionError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ProtocolConflictError)
async def _protocol_conflict(_request: object, exc: ProtocolConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(TransactionUnavailableError)
async def _protocol_tx_missing(
    _request: object, exc: TransactionUnavailableError
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ProtocolMaterializationRequiredError)
async def _protocol_materialize_required(
    _request: object, exc: ProtocolMaterializationRequiredError
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(AuthenticationRequiredError)
async def _auth_error(_request: object, exc: AuthenticationRequiredError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(PermissionDeniedError)
async def _forbid_error(_request: object, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(AccessDeniedError)
async def _object_forbid_error(_request: object, exc: AccessDeniedError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(EmptyPackageError)
async def _empty_package(_request: object, exc: EmptyPackageError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/system/capabilities")
def system_capabilities(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _require("getSystemCapabilities", authorization)
    return capabilities_payload()


@app.post("/api/v1/documents/upload", status_code=202, response_model=None)
async def upload_documents(
    request: Request,
    object_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    authorization: Annotated[str | None, Header()] = None,
    process_id: Annotated[str | None, Form()] = None,
    doc_stage: Annotated[DocStage | None, Form()] = None,
) -> dict[str, object] | JSONResponse:
    try:
        return await _upload_documents(
            request,
            object_id=object_id,
            files=files,
            authorization=authorization,
            process_id=process_id,
            doc_stage=doc_stage,
        )
    finally:
        for upload in files:
            try:
                await upload.close()
            except OSError:
                continue


async def _upload_documents(
    request: Request,
    *,
    object_id: str,
    files: list[UploadFile],
    authorization: str | None,
    process_id: str | None,
    doc_stage: DocStage | None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, caller_object_id = _require("uploadDocuments", authorization)
    normalized_object_id = object_id.strip()
    if not normalized_object_id:
        raise EmptyPackageError("object_id пуст")
    _check_scope(normalized_object_id, caller_object_id)

    workspace = _workspace()
    record = workspace.get(process_id) if process_id else None
    if process_id and record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    if record is not None:
        _check_scope(record.object_id, caller_object_id)
        if record.object_id != normalized_object_id:
            return JSONResponse(status_code=409, content={"detail": "object_id не совпадает"})

    length = request.headers.get("content-length")
    if length is not None and int(length) > MAX_BATCH_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "file_name": "*",
                "reason_code": "BATCH_LIMIT_EXCEEDED",
                "message": f"Content-Length {length} больше лимита {MAX_BATCH_BYTES} Б",
            },
        )
    if not files:
        raise EmptyPackageError("empty package is not a TZ comparison scenario")
    if doc_stage is None:
        return JSONResponse(
            status_code=422,
            content={
                "file_name": "*",
                "reason_code": "UNSUPPORTED_FORMAT",
                "message": "doc_stage обязателен: без стадии файл нельзя привязать к ПД/РД/ИД",
            },
        )

    payloads: list[tuple[UploadCandidate, bytes]] = []
    for upload in files:
        candidate, body = await read_bounded_upload(upload)
        payloads.append((candidate, body if body is not None else b""))
    decision = evaluate_batch(item for item, _body in payloads)
    if decision.rejected and not decision.accepted:
        worst = max(decision.rejected, key=lambda item: item.http_status)
        return JSONResponse(status_code=worst.http_status, content=_rejection_body(worst))

    bodies = {
        item.content_hash: body
        for item, body in payloads
        if item.content_hash is not None
    }

    if record is None:
        completeness = _empty_completeness()
        completeness[doc_stage] = Completeness.UPLOADED
        record = workspace.create(normalized_object_id, completeness)
        attached = _attach_new_files(
            workspace, record, decision.accepted, bodies, doc_stage
        )
        workspace.run_matrix_pipeline(record)
        return _upload_receipt(record, attached, decision.rejected)

    if record.process_state is ProcessState.FINALIZED:
        raise TransitionError("протокол финализирован, дозагрузка запрещена")

    attached = _attach_new_files(
        workspace, record, decision.accepted, bodies, doc_stage
    )
    if not attached:
        return _upload_receipt(record, [], decision.rejected)

    workspace.reopen_for_upload(record)
    workspace.run_matrix_pipeline(record)
    return _upload_receipt(record, attached, decision.rejected)


@app.get("/api/v1/processes/{process_id}/status", response_model=None)
def get_status(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require("getProcessStatus", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    return record.to_status()


@app.post("/api/v1/demo/kit", response_model=None)
def load_demo_kit(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    """Синтетические ПД/РД/ИД. Только учебный токен. Эталон не назначается."""

    if not _is_true(os.environ.get("KONTUR_ALLOW_INSECURE_DEV_AUTH")):
        return JSONResponse(status_code=404, content={"detail": "учебный комплект выключен"})
    _subject, _granted, caller_object_id = _require("loadDemoKit", authorization)
    if caller_object_id is None:
        return JSONResponse(status_code=403, content={"detail": "access denied"})
    try:
        record = install_demo_kit(_workspace(), caller_object_id)
    except FileNotFoundError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    return {
        "process_id": record.process_id,
        "object_id": record.object_id,
        "etalon_file_id": ETALON_FILE_ID,
        "draft_file_id": DRAFT_FILE_ID,
        "note": "Две редакции ПД. Эталон назначает инспектор, файл f-pd.",
    }


@app.get("/api/v1/processes/{process_id}/documents", response_model=None)
def get_documents(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require("getProcessDocuments", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    items = [
        CatalogFile(
            file_id=item.file_id,
            file_hash=item.file_hash,
            filename=item.filename,
            doc_stage=item.doc_stage,
            content=record.blobs[item.file_id],
        )
        for item in record.files
        if item.file_id in record.blobs
    ]
    # Голова шифра и выбор инспектора, не порядок загрузки и не «ред. N».
    return {
        "process_id": process_id,
        "documents": build_document_catalog(
            items,
            inspector_approved_file_ids=frozenset(record.inspector_approved_file_ids),
        ),
    }


@app.get("/api/v1/processes/{process_id}/findings", response_model=None)
def list_findings(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require("listProcessFindings", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    return {
        "process_id": process_id,
        "findings": [
            {
                "finding_id": item.finding_id,
                "rule_code": item.rule_code,
                "finding_status": item.finding_status.value,
                "section": _matrix_section(item.rule_code),
                "rationale": item.rationale,
                "evidence_group_id": item.evidence_group_id,
            }
            for item in record.findings.values()
        ],
    }


def _matrix_section(rule_code: str) -> str | None:
    """Раздел из JSON правила. Неизвестный код не превращается в раздел по префиксу."""

    try:
        rule = _rules().get(rule_code)
    except KeyError:
        return None
    section = rule.get("section")
    if isinstance(section, str) and section.strip():
        return section.strip()
    return None


@app.get(
    "/api/v1/processes/{process_id}/files/{file_id}/pages/{page}.png",
    response_model=None,
)
def get_file_page_png(
    process_id: str,
    file_id: str,
    page: int,
    authorization: Annotated[str | None, Header()] = None,
    bbox: Annotated[str | None, Query()] = None,
) -> Response | JSONResponse:
    _subject, _granted, object_id = _require("getFilePagePng", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    raw = record.blobs.get(file_id)
    if raw is None or not any(item.file_id == file_id for item in record.files):
        return JSONResponse(status_code=404, content={"detail": "файл не найден"})
    try:
        box = parse_bbox(bbox)
        png = render_page_png(raw, page, box)
    except PageRenderError as exc:
        missing = str(exc).startswith("страница")
        return JSONResponse(
            status_code=404 if missing else 400,
            content={"detail": str(exc)},
        )
    return Response(content=png, media_type="image/png")


def _protocol_document(
    process_id: str,
    authorization: str | None,
    operation: str,
    version: int | None = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require(operation, authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    if version is not None:
        if version < 1:
            return JSONResponse(
                status_code=400, content={"detail": "version должен быть >= 1"}
            )
        stored = _workspace().load_protocol_version(record.object_id, version)
        if stored is None:
            return JSONResponse(
                status_code=404, content={"detail": "версия протокола не найдена"}
            )
        return protocol_for_http(stored)
    if protocol_status(record.process_state) is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "протокол не собран: PENDING/PARSING"},
        )
    if record.process_state is ProcessState.FINALIZED:
        protocol_id = record.protocol_id
        if protocol_id is None:
            return JSONResponse(
                status_code=409,
                content={"detail": "финализированный процесс без protocol_id"},
            )
        stored = _workspace().load_protocol(protocol_id)
        if stored is None:
            return JSONResponse(
                status_code=409, content={"detail": "протокол не материализован"}
            )
        return protocol_for_http(stored)
    payload = assemble_protocol(
        protocol_id=record.protocol_id or record.process_id,
        object_id=record.object_id,
        findings=tuple(record.findings.values()),
        completeness=record.completeness,
        files=[{"file_id": item.file_id, "file_hash": item.file_hash} for item in record.files],
        versions={
            "matrix_version": record.matrix_version,
            "model_version": record.model_version,
            "dataset_version": record.dataset_version,
            "git_sha": record.git_sha,
        },
        process_state=record.process_state,
        input_manifest_hash=record.input_manifest_hash,
    )
    return protocol_for_http(payload)


@app.get("/api/v1/processes/{process_id}/protocol", response_model=None)
def get_protocol(
    process_id: str,
    version: int | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    return _protocol_document(process_id, authorization, "getProtocol", version)


@app.get("/api/v1/processes/{process_id}/protocol.docx", response_model=None)
def get_protocol_docx(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    rendered = _protocol_document(process_id, authorization, "getProtocolDocx")
    if isinstance(rendered, JSONResponse):
        return rendered
    return Response(
        content=render_docx(rendered),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="protocol.docx"'},
    )


@app.get("/api/v1/processes/{process_id}/protocol.xml", response_model=None)
def get_protocol_xml(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    rendered = _protocol_document(process_id, authorization, "getProtocolXml")
    if isinstance(rendered, JSONResponse):
        return rendered
    return Response(
        content=render_xml(rendered),
        media_type="application/xml",
        headers={"Content-Disposition": 'attachment; filename="protocol.xml"'},
    )


@app.get("/api/v1/processes/{process_id}/protocol.pdf", response_model=None)
def get_protocol_pdf(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    rendered = _protocol_document(process_id, authorization, "getProtocolPdf")
    if isinstance(rendered, JSONResponse):
        return rendered
    try:
        body = render_pdf(rendered)
    except ProtocolPdfUnavailable as exc:
        return JSONResponse(status_code=501, content={"detail": str(exc)})
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="protocol.pdf"'},
    )


@app.get("/api/v1/processes/{process_id}/audit", response_model=None)
def get_audit(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require("getAuditLog", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    return {
        "process_id": process_id,
        "events": [
            {"actor_id": actor_id, "action": action, "payload": payload}
            for actor_id, action, payload in record.audit.records
        ],
    }


@app.get(
    "/api/v1/processes/{process_id}/findings/{finding_id}/evidence-card",
    response_model=None,
)
def get_evidence_card(
    process_id: str,
    finding_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require("getEvidenceCard", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    finding = _finding_on_record(record, finding_id)
    if finding is None:
        return JSONResponse(status_code=404, content={"detail": "находка не найдена"})
    group = None
    if finding.evidence_group_id is not None:
        group = record.evidence_groups.get(finding.evidence_group_id)
    try:
        rule = _rules().get(finding.rule_code)
    except KeyError:
        rule = {"code": finding.rule_code}
    return build_evidence_card(
        process_id=record.process_id,
        finding=finding,
        group=group,
        rule=rule,
        audit_records=tuple(record.audit.records),
    )


@app.post("/api/v1/findings/{finding_id}/review", response_model=None)
def review_finding(
    finding_id: str,
    body: ReviewRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted, object_id = _require("reviewFinding", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    owner = _record_for_finding(finding_id)
    if owner is None:
        return JSONResponse(status_code=404, content={"detail": "находка не найдена"})
    _check_scope(owner.object_id, object_id)
    finding = _workspace().review_finding(
        finding_id,
        actor=actor_from_roles(subject, granted),
        action=body.action,
        reason_code=body.reason_code,
        comment=body.comment,
    )
    payload: dict[str, object] = {
        "finding_id": finding.finding_id,
        "finding_status": finding.finding_status.value,
        "rule_code": finding.rule_code,
        "evidence_group_id": finding.evidence_group_id,
    }
    if finding.source_id is not None:
        payload["source_id"] = finding.source_id
    if finding.evidence_refs:
        payload["evidence_refs"] = list(finding.evidence_refs)
    if finding.disagreement_kind is not None:
        payload["disagreement_kind"] = finding.disagreement_kind.value
    return payload


def _human_process_action(
    process_id: str,
    body: FinalizeRequest,
    authorization: str | None,
    operation_id: str,
    action: str,
) -> dict[str, object] | JSONResponse:
    subject, granted, object_id = _require(operation_id, authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    actor = actor_from_roles(subject, granted)
    if action == "verify":
        updated = _workspace().start_verification(process_id, actor)
    elif action == "complete":
        updated = _workspace().complete_verification(process_id, actor)
    elif action == "finalize":
        updated = _workspace().finalize(process_id, actor)
    else:
        raise RuntimeError(f"неизвестное действие {action}")
    return updated.to_status()


@app.post("/api/v1/processes/{process_id}/verify", response_model=None)
def start_verification(
    process_id: str,
    body: FinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    return _human_process_action(
        process_id, body, authorization, "startVerification", "verify"
    )


@app.post("/api/v1/processes/{process_id}/complete", response_model=None)
def complete_verification(
    process_id: str,
    body: FinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    return _human_process_action(
        process_id, body, authorization, "completeVerification", "complete"
    )


@app.post("/api/v1/processes/{process_id}/finalize", response_model=None)
def finalize(
    process_id: str,
    body: FinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    return _human_process_action(
        process_id, body, authorization, "finalizeProtocol", "finalize"
    )


@app.post("/api/v1/processes/{process_id}/unfinalize", response_model=None)
def unfinalize_protocol(
    process_id: str,
    body: UnfinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted, object_id = _require("unfinalizeProtocol", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    updated = _workspace().unfinalize(
        process_id, actor_from_roles(subject, granted), body.reason
    )
    return updated.to_status()


@app.post("/api/v1/processes/{process_id}/revisions/{file_id}/select", response_model=None)
def select_revision(
    process_id: str,
    file_id: str,
    body: SelectRevisionRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted, object_id = _require("selectRevision", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    try:
        updated = _workspace().select_revision(
            process_id,
            file_id,
            actor=actor_from_roles(subject, granted),
            comment=body.comment,
        )
    except KeyError:
        return JSONResponse(status_code=404, content={"detail": "файл не найден"})
    return updated.to_status()


@app.post("/api/v1/inspection/{process_id}", status_code=202, response_model=None)
def sync_inspection(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> str | JSONResponse:
    _subject, _granted, object_id = _require("syncInspection", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    updated = _workspace().request_sync(process_id)
    return updated.sync_state.value
