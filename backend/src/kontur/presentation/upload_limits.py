"""Actual-byte limits for the authoritative Python upload boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import BinaryIO

from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kontur.application.intake import MAX_BATCH_BYTES, MAX_FILE_BYTES
from kontur.presentation.auth import parse_bearer
from kontur.presentation.rbac import (
    AuthenticationRequiredError,
    PermissionDeniedError,
    authorize,
)

UPLOAD_PATH = "/api/v1/documents/upload"
READ_CHUNK_BYTES = 1024 * 1024
SPOOL_MEMORY_BYTES = 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_BATCH_BYTES + MULTIPART_OVERHEAD_BYTES
_DEFAULT_MAX_CONCURRENT_UPLOADS = 2
_TOO_LARGE = json.dumps({"detail": "request too large"}, separators=(",", ":")).encode()
_TOO_MANY = json.dumps({"detail": "too many requests"}, separators=(",", ":")).encode()
_UNAUTHORIZED = json.dumps({"detail": "unauthorized"}, separators=(",", ":")).encode()
_FORBIDDEN = json.dumps({"detail": "forbidden"}, separators=(",", ":")).encode()


class UploadLimitExceeded(Exception):
    """A request or file crossed its actual-byte limit or changed between reads."""


@dataclass(frozen=True, slots=True)
class UploadPayload:
    """Bounded upload metadata calculated without retaining the body."""

    size: int
    header: bytes
    digest: str


@dataclass(slots=True)
class _StagedUpload:
    """Own one local spool until ownership moves to the UploadFile."""

    spool: BinaryIO

    def close(self) -> None:
        self.spool.close()

    def release(self) -> BinaryIO:
        spool = self.spool
        self.spool = _ClosedFile()
        return spool


class _ClosedFile:
    """A closed BinaryIO sentinel used after ownership transfer."""

    def close(self) -> None:
        return None


async def _read_metadata(
    upload: UploadFile,
    *,
    max_file_bytes: int,
    chunk_size: int,
    spool: BinaryIO | None = None,
) -> UploadPayload:
    header = bytearray()
    digest = hashlib.sha256()
    size = 0

    while chunk := await upload.read(chunk_size):
        size += len(chunk)
        if size > max_file_bytes:
            raise UploadLimitExceeded
        digest.update(chunk)
        if len(header) < 16:
            header.extend(chunk[: 16 - len(header)])
        if spool is not None:
            spool.write(chunk)

    return UploadPayload(
        size=size,
        header=bytes(header),
        digest=digest.hexdigest(),
    )


async def read_upload_payload(
    upload: UploadFile,
    max_file_bytes: int = MAX_FILE_BYTES,
    chunk_size: int = READ_CHUNK_BYTES,
) -> UploadPayload:
    """Verify two bounded reads and replace the source with a local spool.

    The first pass records metadata only.  The second pass copies into a
    ``SpooledTemporaryFile`` while independently recomputing all metadata.
    Only a verified spool is installed on the UploadFile, so the endpoint's
    existing outer UploadFile cleanup owns and closes every staged body.
    """

    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be non-negative")
    if not 0 < chunk_size <= READ_CHUNK_BYTES:
        raise ValueError(f"chunk_size must be between 1 and {READ_CHUNK_BYTES}")

    expected = await _read_metadata(
        upload,
        max_file_bytes=max_file_bytes,
        chunk_size=chunk_size,
    )
    await upload.seek(0)

    staged = _StagedUpload(
        tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES, mode="w+b")
    )
    original = upload.file
    try:
        actual = await _read_metadata(
            upload,
            max_file_bytes=max_file_bytes,
            chunk_size=chunk_size,
            spool=staged.spool,
        )
        if actual != expected:
            raise UploadLimitExceeded
        staged.spool.seek(0)
        original.close()
        upload.file = staged.release()
    except BaseException:
        staged.close()
        raise

    return expected


async def materialize_upload(
    upload: UploadFile,
    *,
    expected_size: int,
    expected_digest: str,
    max_file_bytes: int = MAX_FILE_BYTES,
    chunk_size: int = READ_CHUNK_BYTES,
) -> bytes:
    """Materialize one verified spool for the current keep_blob API."""

    if expected_size < 0:
        raise ValueError("expected_size must be non-negative")
    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be non-negative")
    if not 0 < chunk_size <= READ_CHUNK_BYTES:
        raise ValueError(f"chunk_size must be between 1 and {READ_CHUNK_BYTES}")
    if expected_size > max_file_bytes:
        raise UploadLimitExceeded

    await upload.seek(0)
    body = bytearray()
    digest = hashlib.sha256()
    size = 0

    while chunk := await upload.read(chunk_size):
        size += len(chunk)
        if size > max_file_bytes or size > expected_size:
            body.clear()
            raise UploadLimitExceeded
        body.extend(chunk)
        digest.update(chunk)

    if size != expected_size or digest.hexdigest() != expected_digest:
        body.clear()
        raise UploadLimitExceeded
    return bytes(body)


def _configured_upload_slots() -> int:
    raw_value = os.getenv("KONTUR_MAX_CONCURRENT_UPLOADS")
    if raw_value is None:
        return _DEFAULT_MAX_CONCURRENT_UPLOADS
    try:
        value = int(raw_value)
    except ValueError:
        return _DEFAULT_MAX_CONCURRENT_UPLOADS
    return value if value > 0 else _DEFAULT_MAX_CONCURRENT_UPLOADS


def _authorization_header(scope: Scope) -> str | None:
    for name, value in scope.get("headers", ()):
        if name.lower() == b"authorization":
            return value.decode("latin-1")
    return None


class ActualUploadLimitMiddleware:
    """Authenticate, bound, and admission-control the upload request stream."""

    def __init__(
        self,
        app: ASGIApp,
        max_batch_bytes: int = MAX_UPLOAD_REQUEST_BYTES,
        max_concurrent_uploads: int | None = None,
    ) -> None:
        slots = (
            _configured_upload_slots()
            if max_concurrent_uploads is None
            else max_concurrent_uploads
        )
        if max_batch_bytes < 0:
            raise ValueError("max_batch_bytes must be non-negative")
        if slots <= 0:
            raise ValueError("max_concurrent_uploads must be positive")

        self.app = app
        self.max_batch_bytes = max_batch_bytes
        self.max_concurrent_uploads = slots
        self._admission_lock = asyncio.Lock()
        self._active_uploads = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != UPLOAD_PATH:
            await self.app(scope, receive, send)
            return

        try:
            context = parse_bearer(_authorization_header(scope))
            authorize("uploadDocuments", context.roles)
        except AuthenticationRequiredError:
            await self._send_json(send, 401, _UNAUTHORIZED)
            return
        except PermissionDeniedError:
            await self._send_json(send, 403, _FORBIDDEN)
            return

        if not await self._try_admit():
            await self._send_json(send, 429, _TOO_MANY)
            return

        response_started = False
        received_bytes = 0

        async def bounded_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_batch_bytes:
                    raise UploadLimitExceeded
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            try:
                await self.app(scope, bounded_receive, tracked_send)
            except UploadLimitExceeded:
                if response_started:
                    raise
                await self._send_json(send, 413, _TOO_LARGE)
        finally:
            await self._release()

    async def _try_admit(self) -> bool:
        async with self._admission_lock:
            if self._active_uploads >= self.max_concurrent_uploads:
                return False
            self._active_uploads += 1
            return True

    async def _release(self) -> None:
        async with self._admission_lock:
            self._active_uploads -= 1

    @staticmethod
    async def _send_json(send: Send, status: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
