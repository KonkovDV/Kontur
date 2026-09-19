"""Actual-byte limits for the authoritative Python upload boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass

from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kontur.application.intake import MAX_BATCH_BYTES, MAX_FILE_BYTES

UPLOAD_PATH = "/api/v1/documents/upload"
READ_CHUNK_BYTES = 1024 * 1024
_DEFAULT_MAX_CONCURRENT_UPLOADS = 2
_TOO_LARGE = json.dumps({"detail": "request too large"}, separators=(",", ":")).encode()
_TOO_MANY = json.dumps({"detail": "too many requests"}, separators=(",", ":")).encode()


class UploadLimitExceeded(Exception):
    """A request or file crossed its actual-byte limit."""


@dataclass(frozen=True, slots=True)
class UploadPayload:
    """A bounded upload body and metadata calculated while reading it."""

    body: bytes
    size: int
    header: bytes
    digest: str


async def read_upload_payload(
    upload: UploadFile,
    max_file_bytes: int = MAX_FILE_BYTES,
    chunk_size: int = READ_CHUNK_BYTES,
) -> UploadPayload:
    """Read one upload incrementally without taking ownership of its lifetime."""

    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be non-negative")
    if not 0 < chunk_size <= READ_CHUNK_BYTES:
        raise ValueError(f"chunk_size must be between 1 and {READ_CHUNK_BYTES}")

    body = bytearray()
    header = bytearray()
    digest = hashlib.sha256()
    size = 0

    while chunk := await upload.read(chunk_size):
        size += len(chunk)
        if size > max_file_bytes:
            body.clear()
            raise UploadLimitExceeded
        body.extend(chunk)
        digest.update(chunk)
        if len(header) < 16:
            header.extend(chunk[: 16 - len(header)])

    return UploadPayload(
        body=bytes(body),
        size=size,
        header=bytes(header),
        digest=digest.hexdigest(),
    )


def _configured_upload_slots() -> int:
    raw_value = os.getenv("KONTUR_MAX_CONCURRENT_UPLOADS")
    if raw_value is None:
        return _DEFAULT_MAX_CONCURRENT_UPLOADS
    try:
        value = int(raw_value)
    except ValueError:
        return _DEFAULT_MAX_CONCURRENT_UPLOADS
    return value if value > 0 else _DEFAULT_MAX_CONCURRENT_UPLOADS


class ActualUploadLimitMiddleware:
    """Bound and admission-control the exact upload route's request stream."""

    def __init__(
        self,
        app: ASGIApp,
        max_batch_bytes: int = MAX_BATCH_BYTES,
        max_concurrent_uploads: int | None = None,
    ) -> None:
        slots = _configured_upload_slots() if max_concurrent_uploads is None else max_concurrent_uploads
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
