"""FastAPI-фасад. Контракт — contracts/openapi.yaml.

Обработка не выполняется в процессе запроса: загрузка принимает файлы,
создаёт процесс и оставляет его в PARSING. Сравнение L1–L7 здесь не
вызывается: экстракторов нет, и статус READY соврал бы.

Аудит-2026-09:
  Добавлен GET /api/v1/system/capabilities (донор AeroBIM capability honesty).
  review_finding ответ дополнен source_id, evidence_refs, disagreement_kind.
"""

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
from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.capabilities import (
    CapStatus,
    Capability,
    engine_health_summary,
    overall_kit_status,
)
from kontur.domain.models import DocStage
from kontur.domain.state_machines import TransitionError
from kontur.domain.status_map import EmptyPackageError
from kontur.domain.statuses import Completeness, ReasonCode
from kontur.presentation.auth import actor_from_roles, parse_bearer
from kontur.presentation.rbac import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    Role,
    authorize,
)

app = FastAPI(title="Инспектор ИИ", version="0.1.0-skeleton")
app.state.workspace = ProcessWorkspace()

# Конфигурация движков по умолчанию (audit-2026-09, донор AeroBIM).
# Заменяется через app.state.capabilities в интеграционных тестах.
_DEFAULT_CAPABILITIES: tuple[Capability, ...] = (
    Capability(name="vector_text", status=CapStatus.AVAILABLE, affects_verdict=True),
    Capability(name="ocr_text", status=CapStatus.AVAILABLE, affects_verdict=True),
    Capability(name="ocr_tables", status=CapStatus.AVAILABLE, affects_verdict=True),
    Capability(name="drawing_analysis", status=CapStatus.AVAILABLE, affects_verdict=True),
    Capability(name="llm_advisory", status=CapStatus.AVAILABLE, affects_verdict=False),
)


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


def _capabilities() -> tuple[Capability, ...]:
    caps = getattr(app.state, "capabilities", None)
    if caps is None:
        return _DEFAULT_CAPABILITIES
    return tuple(caps)


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
def get_capabilities() -> dict[str, object]:
    """Таблица движков (донор AeroBIM capability honesty, audit-2026-09).

    Возвращает ok | degraded | skipped | failed для каждого движка.
    LLM-advisory UNAVAILABLE -> 'skipped', не 'failed' (ADR-003).
    Verdict engine UNAVAILABLE -> 'failed' -> overall_kit_status=BLOCKED.
    Verdict engine DEGRADED -> 'degraded' -> overall_kit_status=DEGRADED.
    Silence is never success (AeroBIM ADR-001).
    """
    caps = _capabilities()
    engines = engine_health_summary(caps)
    kit_status = overall_kit_status(caps)
    affected = [
        cap.name for cap in caps
        if cap.affects_verdict and cap.status is not CapStatus.AVAILABLE
    ]
    return {
        "overall_kit_status": kit_status,
        "engine_status": engines,
        "affected_verdict_engines": affected,
        "advisory": {
            "note": "LLM-advisory failure is 'skipped', never 'failed' (ADR-003)",
        },
    }


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
                "message": f"Content-Length {length} больше лимита {MAX_BATCH_BYTES} Б",
            },
        )
    if not object_id.strip():
        raise EmptyPackageError("object_id пуст")
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
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    if record is None:
        completeness = _empty_completeness()
        completeness[doc_stage] = Completeness.UPLOADED
        record = workspace.create(object_id.strip(), completeness)
    else:
        if record.object_id != object_id.strip():
            return JSONResponse(status_code=409, content={"detail": "object_id не совпадает"})
        workspace.reopen_for_upload(record)

    accepted: list[dict[str, str]] = []
    for item in decision.accepted:
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
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    return record.to_status()


@app.get("/api/v1/processes/{process_id}/protocol", response_model=None)
def get_protocol(
    process_id: str,
    version: int | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    _require("getProtocol", authorization)
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    del version
    return JSONResponse(
        status_code=404,
        content={
            "detail": "протокол не собран: исполняемого извлечения нет, L9 не вызывается"
        },
    )


@app.post("/api/v1/findings/{finding_id}/review", response_model=None)
def review_finding(
    finding_id: str,
    body: ReviewRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted = _require("reviewFinding", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    try:
        finding = _workspace().review_finding(
            finding_id,
            actor=actor_from_roles(subject, granted),
            action=body.action,
            reason_code=body.reason_code,
            comment=body.comment,
        )
    except KeyError:
        return JSONResponse(status_code=404, content={"detail": "находка не найдена"})
    # audit-2026-09: добавлены source_id, evidence_refs, disagreement_kind
    return {
        "finding_id": finding.finding_id,
        "finding_status": finding.finding_status.value,
        "rule_code": finding.rule_code,
        "evidence_group_id": finding.evidence_group_id,
        "source_id": finding.source_id,
        "evidence_refs": list(finding.evidence_refs),
        "disagreement_kind": finding.disagreement_kind.value if finding.disagreement_kind else None,
    }


@app.post("/api/v1/processes/{process_id}/finalize", response_model=None)
def finalize(
    process_id: str,
    body: FinalizeRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object] | JSONResponse:
    subject, granted = _require("finalizeProtocol", authorization)
    if body.inspector_id != subject:
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
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
        raise PermissionDeniedError("inspector_id не совпадает с субъектом токена")
    record = _workspace().get(process_id)
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
    _require("syncInspection", authorization)
    record = _workspace().get(process_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "процесс не найден"})
    updated = _workspace().request_sync(process_id)
    return updated.sync_state.value
