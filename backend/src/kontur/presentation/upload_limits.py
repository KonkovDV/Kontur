"""Actual-byte limits for the authoritative Python upload boundary."""

from __future__ import annotations

import contextvars
import hashlib
import json
from typing import cast

from starlette.datastructures import UploadFile
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from kontur.application.intake import MAX_BATCH_BYTES, MAX_FILE_BYTES

UPLOAD_PATH = "/api/v1/documents/upload"
READ_CHUNK_BYTES = 1024 * 1024
_TOO_LARGE = json.dumps({"detail": "request too large"}, separators=(",", ":")).encode()


class UploadLimitExceeded(Exception):
    """A request or file crossed its actual-byte limit."""


_active_uploads: contextvars.ContextVar[list[UploadFile] | None] = contextvars.ContextVar(
    "bounded_upload_files", default=None
)
_original_read = UploadFile.read


async def _bounded_read(self: UploadFile, size: int = -1) -> bytes:
    tracked = _active_uploads.get()
    if tracked is None or size >= 0:
        return await _original_read(self, size)
    if self not in tracked:
        tracked.append(self)

    chunks: list[bytes] = []
    digest = hashlib.sha256()
    first16 = bytearray()
    total = 0
    while True:
        chunk = await _original_read(self, READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            chunks.clear()
            raise UploadLimitExceeded
        digest.update(chunk)
        if len(first16) < 16:
            first16.extend(chunk[: 16 - len(first16)])
        chunks.append(chunk)
    setattr(self, "actual_size_bytes", total)
    setattr(self, "actual_sha256", digest.hexdigest())
    setattr(self, "actual_first16", bytes(first16))
    payload = b"".join(chunks)
    chunks.clear()
    return payload


def install_bounded_upload_read() -> None:
    """Install the idempotent UploadFile streaming read guard."""

    if UploadFile.read is not _bounded_read:
        UploadFile.read = _bounded_read  # type: ignore[method-assign]


class ActualUploadLimitMiddleware:
    """Count raw http.request bytes before multipart parsing on the exact upload path."""

    def __init__(self, app: ASGIApp, max_batch_bytes: int = MAX_BATCH_BYTES) -> None:
        self.app = app
        self.max_batch_bytes = max_batch_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != UPLOAD_PATH:
            await self.app(scope, receive, send)
            return

        frames: list[Message] = []
        total = 0
        while True:
            message = await receive()
            frames.append(message)
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_batch_bytes:
                    frames.clear()
                    await self._reject(send)
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                return

        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(frames):
                message = frames[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        clean_scope = dict(scope)
        clean_scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower() != b"content-length"
        ]
        uploads: list[UploadFile] = []
        token = _active_uploads.set(uploads)
        response_started = False

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(cast(Scope, clean_scope), replay, guarded_send)
        except UploadLimitExceeded:
            if not response_started:
                await self._reject(send)
        finally:
            frames.clear()
            for upload in uploads:
                await upload.close()
            uploads.clear()
            _active_uploads.reset(token)

    @staticmethod
    async def _reject(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_TOO_LARGE)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _TOO_LARGE})
