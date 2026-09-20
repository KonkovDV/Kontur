"""Actual-byte upload limits at the raw ASGI and UploadFile boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import io
from collections.abc import Awaitable, Callable

import pytest
from starlette.datastructures import UploadFile
from starlette.types import Message, Receive, Scope, Send

from kontur.application.intake import RejectionReason
from kontur.presentation.upload_limits import (
    UPLOAD_PATH,
    ActualUploadLimitMiddleware,
    read_bounded_upload,
)

ASGI = Callable[[Scope, Receive, Send], Awaitable[None]]
DEV_UPLOAD_HEADERS = [(b"authorization", b"Bearer insp-7@obj-1/INSPECTOR")]


@pytest.fixture
def dev_upload_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[bytes, bytes]]:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    return DEV_UPLOAD_HEADERS


def _frames(*chunks: bytes) -> list[Message]:
    return [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]


def _scope(
    *,
    path: str = UPLOAD_PATH,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "client": None,
        "server": None,
        "root_path": "",
    }


async def _invoke(
    app: ASGI,
    frames: list[Message],
    *,
    path: str = UPLOAD_PATH,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> list[Message]:
    queue = list(frames)
    sent: list[Message] = []

    async def receive() -> Message:
        return queue.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    await app(_scope(path=path, headers=headers), receive, send)
    return sent


def _consumer(received: list[Message]) -> ASGI:
    async def downstream(_scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            received.append(message)
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return downstream


def test_exact_raw_bytes_pass_as_original_frames(
    dev_upload_headers: list[tuple[bytes, bytes]],
) -> None:
    frames = _frames(b"12", b"345")
    received: list[Message] = []
    sent = asyncio.run(
        _invoke(
            ActualUploadLimitMiddleware(_consumer(received), 5),
            frames,
            headers=dev_upload_headers,
        )
    )
    assert received == frames
    assert [
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    ] == [204]


def test_limit_plus_one_is_413_with_batch_reason(
    dev_upload_headers: list[tuple[bytes, bytes]],
) -> None:
    received: list[Message] = []
    sent = asyncio.run(
        _invoke(
            ActualUploadLimitMiddleware(_consumer(received), 5),
            _frames(b"12345", b"6"),
            headers=dev_upload_headers,
        )
    )
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert [message["status"] for message in starts] == [413]
    assert RejectionReason.BATCH_LIMIT_EXCEEDED.value in sent[-1]["body"].decode()


@pytest.mark.parametrize(
    "headers",
    [[], [(b"content-length", b"1")]],
    ids=["missing", "understated"],
)
def test_content_length_cannot_bypass_actual_byte_limit(
    headers: list[tuple[bytes, bytes]],
    dev_upload_headers: list[tuple[bytes, bytes]],
) -> None:
    called = False

    async def downstream(_scope: Scope, receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True
        while (await receive()).get("more_body", False):
            pass

    sent = asyncio.run(
        _invoke(
            ActualUploadLimitMiddleware(downstream, 5),
            _frames(b"123", b"456"),
            headers=[*headers, *dev_upload_headers],
        )
    )
    assert called is True
    assert [
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    ] == [413]


def test_other_path_is_untouched() -> None:
    frames = _frames(b"123456")
    received: list[Message] = []
    sent = asyncio.run(
        _invoke(
            ActualUploadLimitMiddleware(_consumer(received), 0),
            frames,
            path="/api/v1/other",
        )
    )
    assert received == frames
    assert sent[0]["status"] == 204


def test_missing_auth_is_401_before_downstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    called = False

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal called
        called = True

    sent = asyncio.run(
        _invoke(ActualUploadLimitMiddleware(downstream, 5), _frames(b"123456"))
    )
    assert called is False
    assert sent[0]["status"] == 401


def test_bounded_read_stops_after_first_overflow_byte() -> None:
    body = b"%PDF-" + (b"x" * 8)
    upload = UploadFile(file=io.BytesIO(body), filename="big.pdf")

    async def _run() -> None:
        candidate, stored = await read_bounded_upload(
            upload, max_file_bytes=5, chunk_size=1
        )
        assert stored is None
        assert candidate.size_bytes == 6
        assert candidate.content_hash is None
        leftover = upload.file.read()
        assert leftover == body[6:]

    asyncio.run(_run())


def test_bounded_read_keeps_hash_under_limit() -> None:
    body = b"%PDF-ok"
    upload = UploadFile(file=io.BytesIO(body), filename="ok.pdf")

    async def _run() -> None:
        candidate, stored = await read_bounded_upload(
            upload, max_file_bytes=16, chunk_size=3
        )
        assert stored == body
        assert candidate.size_bytes == len(body)
        assert candidate.content_hash == hashlib.sha256(body).hexdigest()
        assert candidate.header == b"%PDF-ok"

    asyncio.run(_run())
