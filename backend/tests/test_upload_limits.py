"""Actual-byte upload limits at the raw ASGI and UploadFile boundaries."""

from __future__ import annotations

import asyncio
import hashlib
import io
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from starlette.types import Message, Receive, Scope, Send

from kontur.presentation.upload_limits import (
    READ_CHUNK_BYTES,
    UPLOAD_PATH,
    ActualUploadLimitMiddleware,
    UploadLimitExceeded,
    read_upload_payload,
)

ASGI = Callable[[Scope, Receive, Send], Awaitable[None]]


def _frames(*chunks: bytes) -> list[Message]:
    return [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]


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

    scope: Scope = {
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
    await app(scope, receive, send)
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


def test_exact_raw_bytes_pass_as_original_frames_without_replay() -> None:
    frames = _frames(b"12", b"345")
    received: list[Message] = []
    sent = asyncio.run(
        _invoke(ActualUploadLimitMiddleware(_consumer(received), 5), frames)
    )
    assert received == frames
    assert all(actual is expected for actual, expected in zip(received, frames, strict=True))
    assert [message["status"] for message in sent if message["type"] == "http.response.start"] == [204]


def test_limit_plus_one_produces_one_413() -> None:
    received: list[Message] = []
    sent = asyncio.run(
        _invoke(
            ActualUploadLimitMiddleware(_consumer(received), 5),
            _frames(b"12345", b"6"),
        )
    )
    starts = [message for message in sent if message["type"] == "http.response.start"]
    assert [message["status"] for message in starts] == [413]
    assert sent[-1]["body"] == b'{"detail":"request too large"}'


@pytest.mark.parametrize(
    "headers",
    [[], [(b"content-length", b"1")]],
    ids=["missing", "understated"],
)
def test_content_length_cannot_bypass_actual_byte_limit(
    headers: list[tuple[bytes, bytes]],
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
            headers=headers,
        )
    )
    assert called is True
    assert [message["status"] for message in sent if message["type"] == "http.response.start"] == [413]


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


def test_disconnect_releases_admission_slot() -> None:
    calls = 0

    async def downstream(_scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal calls
        calls += 1
        message = await receive()
        if message["type"] == "http.disconnect":
            return
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ActualUploadLimitMiddleware(
        downstream, max_batch_bytes=5, max_concurrent_uploads=1
    )

    async def scenario() -> list[Message]:
        await _invoke(middleware, [{"type": "http.disconnect"}])
        return await _invoke(middleware, _frames(b"12345"))

    sent = asyncio.run(scenario())
    assert calls == 2
    assert sent[0]["status"] == 204


def test_admission_rejects_before_body_then_allows_after_release() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    bodies: list[bytes] = []

    async def downstream(_scope: Scope, receive: Receive, send: Send) -> None:
        message = await receive()
        bodies.append(message.get("body", b""))
        if len(bodies) == 1:
            entered.set()
            await release.wait()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ActualUploadLimitMiddleware(
        downstream, max_batch_bytes=5, max_concurrent_uploads=1
    )

    async def scenario() -> tuple[list[Message], list[Message]]:
        first = asyncio.create_task(_invoke(middleware, _frames(b"12345")))
        await entered.wait()
        second_reads = 0
        second_sent: list[Message] = []

        async def receive_second() -> Message:
            nonlocal second_reads
            second_reads += 1
            return _frames(b"12345")[0]

        async def send_second(message: Message) -> None:
            second_sent.append(message)

        scope: Scope = {
            "type": "http",
            "path": UPLOAD_PATH,
            "headers": [],
            "method": "POST",
        }
        await middleware(scope, receive_second, send_second)
        assert second_reads == 0
        release.set()
        await first
        third = await _invoke(middleware, _frames(b"12345"))
        return second_sent, third

    rejected, admitted = asyncio.run(scenario())
    assert rejected[0]["status"] == 429
    assert admitted[0]["status"] == 204
    assert bodies == [b"12345", b"12345"]


def test_downstream_limit_error_before_response_becomes_single_413() -> None:
    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        raise UploadLimitExceeded

    sent = asyncio.run(
        _invoke(ActualUploadLimitMiddleware(downstream, 5), _frames(b""))
    )
    assert [message["status"] for message in sent if message["type"] == "http.response.start"] == [413]


def test_downstream_limit_error_after_start_is_reraised_without_second_start() -> None:
    sent: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        raise UploadLimitExceeded

    async def scenario() -> None:
        queue = _frames(b"")

        async def receive() -> Message:
            return queue.pop(0)

        async def send(message: Message) -> None:
            sent.append(message)

        scope: Scope = {"type": "http", "path": UPLOAD_PATH, "headers": []}
        with pytest.raises(UploadLimitExceeded):
            await ActualUploadLimitMiddleware(downstream, 5)(scope, receive, send)

    asyncio.run(scenario())
    assert [message["status"] for message in sent if message["type"] == "http.response.start"] == [204]


class _TrackedUpload:
    def __init__(self, body: bytes) -> None:
        self._file = io.BytesIO(body)
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._file.read(size)


def test_read_upload_payload_is_incremental_and_records_metadata() -> None:
    body = b"0123456789abcdef-more"
    upload = _TrackedUpload(body)
    payload = asyncio.run(
        read_upload_payload(upload, max_file_bytes=len(body), chunk_size=3)  # type: ignore[arg-type]
    )
    assert payload.body == body
    assert payload.size == len(body)
    assert payload.header == body[:16]
    assert payload.digest == hashlib.sha256(body).hexdigest()
    assert upload.read_sizes
    assert set(upload.read_sizes) == {3}


def test_read_upload_payload_exact_limit_passes() -> None:
    upload = UploadFile(filename="a.pdf", file=io.BytesIO(b"12345"))
    payload = asyncio.run(read_upload_payload(upload, max_file_bytes=5, chunk_size=2))
    assert payload.body == b"12345"
    assert payload.size == 5


def test_read_upload_payload_limit_plus_one_raises() -> None:
    upload = UploadFile(filename="a.pdf", file=io.BytesIO(b"123456"))
    with pytest.raises(UploadLimitExceeded):
        asyncio.run(read_upload_payload(upload, max_file_bytes=5, chunk_size=2))


@pytest.mark.parametrize(
    ("limit", "chunk_size"),
    [(-1, 1), (1, 0), (1, READ_CHUNK_BYTES + 1)],
)
def test_read_upload_payload_rejects_invalid_limits(
    limit: int, chunk_size: int
) -> None:
    upload = UploadFile(filename="a.pdf", file=io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        asyncio.run(
            read_upload_payload(
                upload, max_file_bytes=limit, chunk_size=chunk_size
            )
        )


def test_real_multipart_is_rejected_before_endpoint_or_workspace() -> None:
    isolated = FastAPI()
    isolated.add_middleware(
        ActualUploadLimitMiddleware,
        max_batch_bytes=32,
        max_concurrent_uploads=1,
    )
    isolated.state.endpoint_calls = 0
    isolated.state.workspace_created = False

    @isolated.post(UPLOAD_PATH)
    async def sentinel(request: Request) -> dict[str, bool]:
        isolated.state.endpoint_calls += 1
        isolated.state.workspace_created = True
        await request.form()
        return {"ok": True}

    with TestClient(isolated) as client:
        response = client.post(
            UPLOAD_PATH,
            data={"object_id": "obj-1"},
            files=[("files", ("a.pdf", b"x", "application/pdf"))],
        )
    assert response.status_code == 413
    assert response.json() == {"detail": "request too large"}
    assert isolated.state.endpoint_calls == 0
    assert isolated.state.workspace_created is False
