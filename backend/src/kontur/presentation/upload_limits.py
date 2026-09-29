"""Actual-byte limits at the Python upload boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kontur.application import intake as intake_mod
from kontur.application.intake import (
    BATCH_SCOPE,
    MAX_BATCH_BYTES,
    RejectionReason,
    UploadCandidate,
)
from kontur.presentation.auth import parse_bearer
from kontur.presentation.rbac import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    authorize,
)

UPLOAD_PATH = "/api/v1/documents/upload"
READ_CHUNK_BYTES = 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_BATCH_BYTES + MULTIPART_OVERHEAD_BYTES


class UploadLimitExceeded(Exception):
    """Request body crossed the declared batch byte limit."""


def _json_bytes(payload: Mapping[str, str]) -> bytes:
    return json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def batch_limit_body(size: int, limit: int) -> bytes:
    return _json_bytes(
        {
            "file_name": BATCH_SCOPE,
            "reason_code": RejectionReason.BATCH_LIMIT_EXCEEDED.value,
            "message": f"{size} Б больше лимита {limit} Б",
        }
    )


def _authorization_header(scope: Scope) -> str | None:
    raw: Any = scope.get("headers", ())
    if not isinstance(raw, (list, tuple)):
        return None
    for item in raw:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        name, value = item
        if not isinstance(name, bytes) or not isinstance(value, bytes):
            continue
        if name.lower() == b"authorization":
            return value.decode("latin-1")
    return None


async def read_bounded_upload(
    upload: UploadFile,
    *,
    max_file_bytes: int | None = None,
    chunk_size: int = READ_CHUNK_BYTES,
) -> tuple[UploadCandidate, bytes | None]:
    """Hash and materialize a file, stopping after the first byte past the limit."""

    limit = intake_mod.MAX_FILE_BYTES if max_file_bytes is None else max_file_bytes
    if limit < 0:
        raise ValueError("max_file_bytes must be non-negative")
    if not 0 < chunk_size <= READ_CHUNK_BYTES:
        raise ValueError(f"chunk_size must be between 1 and {READ_CHUNK_BYTES}")
    name = upload.filename or "unnamed"
    digest = hashlib.sha256()
    header = bytearray()
    parts: list[bytes] = []
    size = 0
    while chunk := await upload.read(chunk_size):
        size += len(chunk)
        if size > limit:
            return (
                UploadCandidate(
                    filename=name,
                    size_bytes=size,
                    header=bytes(header) if header else None,
                    content_hash=None,
                ),
                None,
            )
        digest.update(chunk)
        if len(header) < 16:
            header.extend(chunk[: 16 - len(header)])
        parts.append(chunk)
    return (
        UploadCandidate(
            filename=name,
            size_bytes=size,
            header=bytes(header) if header else None,
            content_hash=digest.hexdigest(),
        ),
        b"".join(parts),
    )


class ActualUploadLimitMiddleware:
    """Authenticate upload, then bound actual `http.request` bytes."""

    def __init__(
        self,
        app: ASGIApp,
        max_batch_bytes: int = MAX_UPLOAD_REQUEST_BYTES,
    ) -> None:
        if max_batch_bytes < 0:
            raise ValueError("max_batch_bytes must be non-negative")
        self.app = app
        self.max_batch_bytes = max_batch_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != UPLOAD_PATH:
            await self.app(scope, receive, send)
            return
        try:
            context = parse_bearer(_authorization_header(scope))
            authorize("uploadDocuments", context.roles)
        except AuthenticationRequiredError as exc:
            await self._send_json(send, 401, _json_bytes({"detail": str(exc)}))
            return
        except PermissionDeniedError as exc:
            await self._send_json(send, 403, _json_bytes({"detail": str(exc)}))
            return

        received_bytes = 0
        response_started = False

        async def bounded_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                chunk = body if isinstance(body, bytes) else b""
                received_bytes += len(chunk)
                if received_bytes > self.max_batch_bytes:
                    raise UploadLimitExceeded
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, tracked_send)
        except UploadLimitExceeded:
            if response_started:
                raise
            await self._send_json(
                send, 413, batch_limit_body(received_bytes, self.max_batch_bytes)
            )

    @staticmethod
    async def _send_json(send: Send, status: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
