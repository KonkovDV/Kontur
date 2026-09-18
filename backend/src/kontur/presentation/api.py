"""FastAPI-\u0444\u0430\u0441\u0430\u0434. \u041a\u043e\u043d\u0442\u0440\u0430\u043a\u0442 \u2014 contracts/openapi.yaml.\n\n\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u043d\u0435 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f \u0432 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0435 \u0437\u0430\u043f\u0440\u043e\u0441\u0430: \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u043f\u0440\u0438\u043d\u0438\u043c\u0430\u0435\u0442 \u0444\u0430\u0439\u043b\u044b,\n\u0441\u043e\u0437\u0434\u0430\u0451\u0442 \u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u0438 \u043e\u0441\u0442\u0430\u0432\u043b\u044f\u0435\u0442 \u0435\u0433\u043e \u0432 PARSING. \u0421\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u0435 L1\u2013L7 \u0437\u0434\u0435\u0441\u044c \u043d\u0435\n\u0432\u044b\u0437\u044b\u0432\u0430\u0435\u0442\u0441\u044f: \u044d\u043a\u0441\u0442\u0440\u0430\u043a\u0442\u043e\u0440\u043e\u0432 \u043d\u0435\u0442, \u0438 \u0441\u0442\u0430\u0442\u0443\u0441 READY \u0441\u043e\u0432\u0440\u0430\u043b \u0431\u044b.\nGET /protocol \u0441\u043e\u0431\u0438\u0440\u0430\u0435\u0442 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a \u0438\u0437 ProcessRecord \u043f\u043e\u0441\u043b\u0435 READY; PENDING/PARSING\n\u0434\u0430\u044e\u0442 404. AUTO_NO_DIFFERENCE \u043d\u0430 \u044d\u0442\u043e\u043c \u043f\u0440\u043e\u0432\u043e\u0434\u0435 \u043d\u0435\u0442.\nGET /audit \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 in-memory \u0436\u0443\u0440\u043d\u0430\u043b \u0438\u043d\u0441\u043f\u0435\u043a\u0442\u043e\u0440\u0430 (GAP-EDIT \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e).\n"""

from __future__ import annotations

import hashlib
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kontur.application.intake import (
    MAX_BATCH_BYTES,
    Rejection,
    UploadCandidate,
    evaluate_batch,
)
from kontur.application.protocol import assemble_protocol
from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.capabilities import capabilities_payload
from kontur.domain.models import DocStage
from kontur.domain.state_machines import TransitionError
from kontur.domain.status_map import EmptyPackageError, protocol_status
from kontur.domain.statuses import Completeness, ReasonCode
from kontur.presentation.auth import actor_from_roles, parse_bearer
from kontur.presentation.rbac import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    Role,
    authorize,
)

app = FastAPI(title="\u0418\u043d\u0441\u043f\u0435\u043a\u0442\u043e\u0440 \u0418\u0418", version="0.1.0-skeleton")
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


def _require(operation_id: str, authorization: str | None) -> tuple[str, frozenset[Role]]:
    subject, roles = parse_bearer(authorization)
    granted = authorize(operation_id, roles)
    return subject, granted


def _rejection_body(item: Rejection) -> dict[str, str]:
    return {
        "file_name": item.filename,
        "reason_code": item.reason.value,
        "message": item.detail,
    }


@app.exception_handler(TransitionError)
async def _transition_error(_request: Request, exc: TransitionError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(AuthenticationRequiredError)
async def _auth_error(_request: Request, exc: AuthenticationRequiredError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc)})


@app.exception_handler(PermissionDeniedError)
async def _forbid_error(_request: Request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(EmptyPackageError)
async def _empty_package(_request: Request, exc: EmptyPackageError) -> JSONResponse:
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
    _require("uploadDocuments", authorization)
    length = request.headers.get("content-length")
    if length is not None and int(length) > MAX_BATCH_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "file_name": "*",
                "reason_code": "BATCH_LIMIT_EXCEEDED",
                "message": f"Content-Length {length} \u0431\u043e\u043b\u044c\u0448\u0435 \u043b\u0438\u043c\u0438\u0442\u0430 {MAX_BATCH_BYTES} \u0411",
            },
        )
    if not object_id.strip():
        raise EmptyPackageError("object_id \u043f\u0443\u0441\u0442")
    if not files:
        raise EmptyPackageError("empty package is not a TZ comparison scenario")
    if doc_stage is None:
        return JSONResponse(
            status_code=422,
            content={
                "file_name": "*",
                "reason_code": "UNSUPPORTED_FORMAT",
                "message": "doc_stage \u043e\u0431\u044f\u0437\u0430\u0442\u0435\u043b\u0435\u043d: \u0431\u0435\u0437 \u0441\u0442\u0430\u0434\u0438\u0438 \u0444\u0430\u0439\u043b \u043d\u0435\u043b\u044c\u0437\u044f \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u0442\u044c \u043a \u041f\u0414/\u0420\u0414/\u0418\u0414",
            },
        )

    payloads: list[tuple[UploadCandidate, bytes]] = []
    for upload in files:
        name = upload.filename or "unnamed"
        body = await upload.read()
        candidate = UploadCandidate(
            filename=name,
            size_bytes=len(body),
            header=body[:16],
            content_hash=hashlib.sha256(body).hexdigest(),
        )
        payloads.append((candidate, body))
    decision = evaluate_batch(item for item, _body in payloads)
    if decision.rejected and not decision.accepted:
        worst = max(decision.rejected, key=lambda item: item.http_status)
        return JSONResponse(status_code=worst.http_status, content=_rejection_body(worst))

    workspace = _workspace()
    record = workspace.get(process_id) if process_id else None
    if process_id and record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    if record is None:
        completeness = _empty_completeness()
        completeness[doc_stage] = Completeness.UPLOADED
        record = workspace.create(object_id.strip(), completeness)
    else:
        if record.object_id != object_id.strip():
            return JSONResponse(status_code=409, content={"detail": "object_id \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442"})
        workspace.reopen_for_upload(record)

    accepted: list[dict[str, str]] = []
    for item in decision.accepted:
        digest = item.content_hash
        if digest is None:
            raise RuntimeError("\u043f\u0440\u0438\u043d\u044f\u0442\u044b\u0439 \u0444\u0430\u0439\u043b \u043e\u0431\u044f\u0437\u0430\u043d \u0438\u043c\u0435\u0442\u044c SHA-256")
        stored = AcceptedFile(
            file_id=str(uuid4()),
            file_hash=digest,
            filename=item.filename,
            doc_stage=doc_stage,
            size_bytes=item.size_bytes,
        )
        workspace.attach_file(record, stored)
        accepted.append({"file_id": stored.file_id, "file_hash": stored.file_hash})

    return {
        "process_id": record.process_id,
        "accepted": accepted,
        "rejected": [_rejection_body(item) for item in decision.rejected],
    }


@app.get("/api/v1/processes/{process_id}/status", response_model=None)
def get_status(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _require("getProcessStatus", authorization)
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    return record.to_status()


@app.get("/api/v1/processes/{process_id}/protocol", response_model=None)
def get_protocol(
    process_id: str,
    version: int | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    _require("getProtocol", authorization)
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    del version
    if protocol_status(record.process_state) is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "\u043f\u0440\u043e\u0442\u043e\u043a\u043e\u043b \u043d\u0435 \u0441\u043e\u0431\u0440\u0430\u043d: PENDING/PARSING"},
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
    """\u0416\u0443\u0440\u043d\u0430\u043b \u043f\u0440\u0430\u0432\u043e\u043a \u0438\u043d\u0441\u043f\u0435\u043a\u0442\u043e\u0440\u0430 \u0434\u043b\u044f \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430 (GAP-EDIT, \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e).\n\n    \u0418\u043d-memory \u0432\u0430\u0440\u0438\u0430\u043d\u0442: \u043f\u043e\u0441\u043b\u0435 \u0440\u0435\u0441\u0442\u0430\u0440\u0442\u0430 \u0436\u0443\u0440\u043d\u0430\u043b \u043f\u0443\u0441\u0442. \u041f\u043e\u043b\u043d\u0430\u044f \u043f\u0435\u0440\u0441\u0438\u0441\u0442\u0435\u043d\u0442\u043d\u043e\u0441\u0442\u044c \u2014 Gate L\n    (\u043e\u0442\u0434\u0435\u043b\u044c\u043d\u0430\u044f `user_action_log` \u0442\u0430\u0431\u043b\u0438\u0446\u0430 \u0441 timestamp).
    """
    _require("getAuditLog", authorization)
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    events = [
        {"seq": i, "actor_id": actor_id, "action": action, "payload": payload}
        for i, (actor_id, action, payload) in enumerate(record.audit.records)
    ]
    return {"process_id": process_id, "total": len(events), "events": events}


@app.post("/api/v1/findings/{finding_id}/review", response_model=None)
def review_finding(
    finding_id: str,
    body: ReviewRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted = _require("reviewFinding", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442 \u0441 \u0441\u0443\u0431\u044a\u0435\u043a\u0442\u043e\u043c \u0442\u043e\u043a\u0435\u043d\u0430")
    try:
        finding = _workspace().review_finding(
            finding_id,
            actor=actor_from_roles(subject, granted),
            action=body.action,
            reason_code=body.reason_code,
            comment=body.comment,
        )
    except KeyError:
        return JSONResponse(status_code=404, content={"detail": "\u043d\u0430\u0445\u043e\u0434\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430"})
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


@app.post("/api/v1/processes/{process_id}/finalize", response_model=None)
def finalize(
    process_id: str,
    body: FinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted = _require("finalizeProtocol", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442 \u0441 \u0441\u0443\u0431\u044a\u0435\u043a\u0442\u043e\u043c \u0442\u043e\u043a\u0435\u043d\u0430")
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    updated = _workspace().finalize(process_id, actor_from_roles(subject, granted))
    return updated.to_status()


@app.post("/api/v1/processes/{process_id}/unfinalize", response_model=None)
def unfinalize_protocol(
    process_id: str,
    body: UnfinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted = _require("unfinalizeProtocol", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442 \u0441 \u0441\u0443\u0431\u044a\u0435\u043a\u0442\u043e\u043c \u0442\u043e\u043a\u0435\u043d\u0430")
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    updated = _workspace().unfinalize(
        process_id, actor_from_roles(subject, granted), body.reason
    )
    return updated.to_status()


@app.post("/api/v1/inspection/{process_id}", status_code=202, response_model=None)
def sync_inspection(
    process_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> str | JSONResponse:
    _require("syncInspection", authorization)
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "\u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"})
    updated = _workspace().request_sync(process_id)
    return updated.sync_state.value
