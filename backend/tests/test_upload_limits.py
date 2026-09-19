"""Actual-byte upload limits without large fixtures."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable

import pytest
from starlette.datastructures import UploadFile

from kontur.presentation import upload_limits
from kontur.presentation.upload_limits import ActualUploadLimitMiddleware, UploadLimitExceeded


def _run(
    frames: Iterable[dict[str, object]],
    *,
    path: str = "/api/v1/documents/upload",
    limit: int = 5,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    received: list[dict[str, object]] = []
    sent: list[dict[str, object]] = []
    queue = list(frames)

    async def downstream(scope, receive, send):  # type: ignore[no-untyped-def]
        del scope
        while True:
            message = await receive()
            received.append(message)
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():  # type: ignore[no-untyped-def]
        return queue.pop(0)

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    scope = {"type": "http", "path": path, "headers": [(b"content-length", b"1")]}
    asyncio.run(ActualUploadLimitMiddleware(downstream, limit)(scope, receive, send))
    return received, sent


def _frames(*chunks: bytes) -> list[dict[str, object]]:
    return [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]


def test_raw_frames_ignore_missing_or_understated_length() -> None:
    received, sent = _run(_frames(b"123", b"456"))
    assert received == []
    assert sent[0]["status"] == 413
    assert sent[1]["body"] == b'{"detail":"request too large"}'


def test_raw_frames_exact_limit_passes_and_plus_one_rejects() -> None:
    received, sent = _run(_frames(b"12", b"345"))
    assert b"".join(message["body"] for message in received) == b"12345"
    assert sent[0]["status"] == 204
    _, rejected = _run(_frames(b"12345", b"6"))
    assert rejected[0]["status"] == 413


def test_other_path_is_untouched() -> None:
    received, sent = _run(_frames(b"123456"), path="/api/v1/other")
    assert received[0]["body"] == b"123456"
    assert sent[0]["status"] == 204


def test_upload_file_read_is_incremental_and_records_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_limits, "MAX_FILE_BYTES", 8)
    upload = UploadFile(filename="a.pdf", file=__import__("io").BytesIO(b"%PDF-abc"))
    tracked: list[UploadFile] = []
    token = upload_limits._active_uploads.set(tracked)  # noqa: SLF001
    try:
        payload = asyncio.run(upload_limits._bounded_read(upload))  # noqa: SLF001
    finally:
        upload_limits._active_uploads.reset(token)  # noqa: SLF001
    assert payload == b"%PDF-abc"
    assert getattr(upload, "actual_size_bytes") == 8
    assert getattr(upload, "actual_sha256") == hashlib.sha256(payload).hexdigest()
    assert getattr(upload, "actual_first16") == payload


def test_upload_file_stops_at_limit_plus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_limits, "MAX_FILE_BYTES", 4)
    upload = UploadFile(filename="a.pdf", file=__import__("io").BytesIO(b"12345"))
    tracked: list[UploadFile] = []
    token = upload_limits._active_uploads.set(tracked)  # noqa: SLF001
    try:
        with pytest.raises(UploadLimitExceeded):
            asyncio.run(upload_limits._bounded_read(upload))  # noqa: SLF001
    finally:
        upload_limits._active_uploads.reset(token)  # noqa: SLF001
