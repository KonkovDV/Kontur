"""Таймаут разбора PDF: исключение, не тихий успех. SIGKILL не используем."""

from __future__ import annotations

import asyncio
import time

import pytest

from kontur.infrastructure.pdf_guard import PdfParseTimeoutError, run_pdf_parse, run_pdf_parse_sync


def _ok(data: bytes) -> str:
    return data.decode("ascii")


def _slow(data: bytes) -> str:
    time.sleep(0.4)
    return data.decode("ascii")


def test_sync_success_returns_parser_result() -> None:
    assert run_pdf_parse_sync(_ok, b"pdf", timeout_s=1.0) == "pdf"


def test_sync_timeout_does_not_wait_for_worker() -> None:
    started = time.perf_counter()
    with pytest.raises(PdfParseTimeoutError, match="превысил"):
        run_pdf_parse_sync(_slow, b"pdf", timeout_s=0.05)
    assert time.perf_counter() - started < 0.3


def test_async_timeout_raises_typed_error() -> None:
    async def _run() -> None:
        with pytest.raises(PdfParseTimeoutError, match="превысил"):
            await run_pdf_parse(_slow, b"pdf", timeout_s=0.05)

    asyncio.run(_run())


def test_async_success() -> None:
    async def _run() -> str:
        return await run_pdf_parse(_ok, b"ok", timeout_s=1.0)

    assert asyncio.run(_run()) == "ok"


def test_non_positive_timeout_is_configuration_error() -> None:
    with pytest.raises(ValueError, match="положительным"):
        run_pdf_parse_sync(_ok, b"x", timeout_s=0)
