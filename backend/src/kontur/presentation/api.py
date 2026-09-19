"""FastAPI-фасад с RBAC и fail-closed object scope для каждого процесса."""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kontur.application.intake import (
    MAX_BATCH_BYTES,
    MAX_FILE_BYTES,
    Rejection,
    UploadCandidate,
    evaluate_batch,
)
from kontur.application.protocol import assemble_protocol
from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.capabilities import capabilities_payload
from kontur.domain.models import DocStage
from kontur.domain.state_machines import TransitionError
from kontur.domain.status_map import EmptyPackageError, protocol_status
from kontur.domain.statuses import Completeness, ReasonCode
from kontur.infrastructure.access_control import AccessDeniedError, check_object_access
from kontur.presentation.auth import actor_from_roles, parse_bearer
from kontur.presentation.rbac import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    Role,
    authorize,
)
from kontur.presentation.upload_limits import (
    ActualUploadLimitMiddleware,
    UploadLimitExceeded,
    materialize_upload,
    read_upload_payload,
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


@app.exception_handler(TransitionError)
async def _transition_error(_request: object, exc: TransitionError) -> JSONResponse:
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
    object_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()],
    authorization: Annotated[str | None, Header()] = None,
    process_id: Annotated[str | None, Form()] = None,
    doc_stage: Annotated[DocStage | None, Form()] = None,
) -> dict[str, object] | JSONResponse:
    payloads: list[tuple[UploadCandidate, UploadFile]] = []
    try:
        _subject, _granted, caller_object_id = _require(
            "uploadDocuments", authorization
        )
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
                return JSONResponse(
                    status_code=409, content={"detail": "object_id не совпадает"}
                )

        if not files:
            raise EmptyPackageError("empty package is not a TZ comparison scenario")
        if doc_stage is None:
            return JSONResponse(
                status_code=422,
                content={
                    "file_name": "*",
                    "reason_code": "UNSUPPORTED_FORMAT",
                    "message": (
                        "doc_stage обязателен: без стадии файл нельзя привязать к ПД/РД/ИД"
                    ),
                },
            )

        batch_size = 0
        for upload in files:
            name = upload.filename or "unnamed"
            payload = await read_upload_payload(
                upload,
                max_file_bytes=MAX_FILE_BYTES,
            )
            batch_size += payload.size
            if batch_size > MAX_BATCH_BYTES:
                raise UploadLimitExceeded
            candidate = UploadCandidate(
                filename=name,
                size_bytes=payload.size,
                header=payload.header,
                content_hash=payload.digest,
            )
            payloads.append((candidate, upload))

        decision = evaluate_batch(item for item, _upload in payloads)
        if decision.rejected:
            worst = max(decision.rejected, key=lambda item: item.http_status)
            return JSONResponse(
                status_code=worst.http_status,
                content=_rejection_body(worst),
            )

        verified_files: list[tuple[AcceptedFile, bytes]] = []
        for item in decision.accepted:
            digest = item.content_hash
            if digest is None:
                raise RuntimeError("принятый файл обязан иметь SHA-256")
            upload = next(
                upload
                for candidate, upload in payloads
                if candidate is item
            )
            body = await materialize_upload(
                upload,
                expected_size=item.size_bytes,
                expected_digest=digest,
                max_file_bytes=MAX_FILE_BYTES,
            )
            verified_files.append(
                (
                    AcceptedFile(
                        file_id=str(uuid4()),
                        file_hash=digest,
                        filename=item.filename,
                        doc_stage=doc_stage,
                        size_bytes=item.size_bytes,
                    ),
                    body,
                )
            )

        if record is None:
            completeness = _empty_completeness()
            completeness[doc_stage] = Completeness.UPLOADED
            record = workspace.create(normalized_object_id, completeness)
        else:
            workspace.reopen_for_upload(record)

        accepted: list[dict[str, str]] = []
        for stored, body in verified_files:
            try:
                if workspace.attach_file(record, stored):
                    workspace.keep_blob(record, stored.file_id, body)
                    accepted.append(
                        {"file_id": stored.file_id, "file_hash": stored.file_hash}
                    )
            finally:
                del body

        workspace.run_matrix_pipeline(record)
        return {
            "process_id": record.process_id,
            "accepted": accepted,
            "rejected": [],
        }
    finally:
        payloads.clear()
        for upload in files:
            try:
                await upload.close()
            except Exception:  # noqa: BLE001 - close every upload best-effort
                pass


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


@app.get("/api/v1/processes/{process_id}/protocol", response_model=None)
def get_protocol(
    process_id: str,
    version: int | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _subject, _granted, object_id = _require("getProtocol", authorization)
    record = _record_for_access(process_id, object_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    del version
    if protocol_status(record.process_state) is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "протокол не собран: PENDING/PARSING"},
        )
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
    raw_sections = payload["sections"]
    if not isinstance(raw_sections, dict):
        raise TypeError("assemble_protocol: sections")
    sections = {str(key): value for key, value in raw_sections.items()}
    sections.pop("preliminary_no_difference", None)
    payload["sections"] = sections
    return payload


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
