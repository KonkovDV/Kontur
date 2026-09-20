"""Таймаут разбора PDF: исключение, не тихий успех. Дочерний процесс убивается."""

from __future__ import annotations

import asyncio
import time

import pytest

from kontur.infrastructure.pdf_guard import PdfParseTimeoutError, run_pdf_parse, run_pdf_parse_sync


def _ok(data: bytes) -> str:
    return data.decode("ascii")


def _slow(data: bytes) -> str:
    time.sleep(10)
    return data.decode("ascii")


def test_sync_success_returns_parser_result() -> None:
    assert run_pdf_parse_sync(_ok, b"pdf", timeout_s=15.0) == "pdf"


def test_sync_timeout_does_not_wait_for_worker() -> None:
    started = time.perf_counter()
    with pytest.raises(PdfParseTimeoutError, match="превысил"):
        run_pdf_parse_sync(_slow, b"pdf", timeout_s=0.2)
    assert time.perf_counter() - started < 3.0


def test_async_timeout_raises_typed_error() -> None:
    async def _run() -> None:
        with pytest.raises(PdfParseTimeoutError, match="превысил"):
            await run_pdf_parse(_slow, b"pdf", timeout_s=0.2)

    asyncio.run(_run())


def test_async_success() -> None:
    async def _run() -> str:
        return await run_pdf_parse(_ok, b"ok", timeout_s=15.0)

    assert asyncio.run(_run()) == "ok"


def test_non_positive_timeout_is_configuration_error() -> None:
    with pytest.raises(ValueError, match="положительным"):
        run_pdf_parse_sync(_ok, b"x", timeout_s=0)


def _raises(data: bytes) -> str:
    del data
    raise ValueError("corrupt pdf")


def test_parser_exception_propagates() -> None:
    with pytest.raises(ValueError, match="corrupt pdf"):
        run_pdf_parse_sync(_raises, b"x", timeout_s=15.0)


def test_timeout_error_has_no_process_id() -> None:
    with pytest.raises(PdfParseTimeoutError) as caught:
        run_pdf_parse_sync(_slow, b"pdf", timeout_s=0.2)
    assert not hasattr(caught.value, "process_id")
