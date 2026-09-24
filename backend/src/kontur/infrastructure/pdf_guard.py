"""Таймаут разбора PDF в дочернем процессе.

pdfium и Tesseract-render живут не в потоке API: по истечении лимита процесс
terminate/kill, а не «подождём поток». Тишина не считается успехом:
PdfParseTimeoutError. Две повторные попытки только на таймаут. Имя
`process_id` в исключении не используем — это идентификатор процесса сверки, не PID.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import time
from collections.abc import Callable
from functools import partial
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import TypeVar

T = TypeVar("T")

DEFAULT_PDF_PARSE_TIMEOUT_S = 30.0
_JOIN_S = 2.0
_POLL_S = 0.05
_PARSE_ATTEMPTS = 3


def pdf_parse_timeout_s() -> float:
    """Лимит разбора. Пакетный прогон задаёт KONTUR_PDF_PARSE_TIMEOUT_S."""

    raw = os.environ.get("KONTUR_PDF_PARSE_TIMEOUT_S")
    if raw is None or not raw.strip():
        return DEFAULT_PDF_PARSE_TIMEOUT_S
    value = float(raw)
    if value <= 0:
        raise ValueError("KONTUR_PDF_PARSE_TIMEOUT_S должен быть положительным")
    return value


class PdfParseTimeoutError(TimeoutError):
    """Разбор PDF не уложился в отведённое время."""


def _pdf_parse_worker(
    parser: Callable[[bytes], object],
    data: bytes,
    conn: Connection,
) -> None:
    try:
        conn.send(("ok", parser(data)))
    except Exception as exc:
        conn.send(("err", exc))
    finally:
        conn.close()


def _ensure_dead(proc: BaseProcess) -> None:
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=_JOIN_S)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=_JOIN_S)
    else:
        proc.join(timeout=_JOIN_S)


def run_pdf_parse_sync(
    parser: Callable[[bytes], T],
    data: bytes,
    *,
    timeout_s: float = DEFAULT_PDF_PARSE_TIMEOUT_S,
) -> T:
    if timeout_s <= 0:
        raise ValueError("timeout_s должен быть положительным")
    error: PdfParseTimeoutError | None = None
    for _attempt in range(_PARSE_ATTEMPTS):
        try:
            return _parse_once(parser, data, timeout_s=timeout_s)
        except PdfParseTimeoutError as exc:
            error = exc
    assert error is not None
    raise error


def _parse_once(
    parser: Callable[[bytes], T],
    data: bytes,
    *,
    timeout_s: float,
) -> T:
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_pdf_parse_worker,
        args=(parser, data, child),
        name="kontur-pdf",
    )
    proc.start()
    child.close()
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if parent.poll(min(_POLL_S, remaining)):
                status, payload = parent.recv()
                if status == "ok":
                    return payload  # type: ignore[no-any-return]
                if status == "err" and isinstance(payload, BaseException):
                    raise payload
                raise RuntimeError(f"неизвестный статус PDF-worker {status!r}")
            if not proc.is_alive():
                raise ValueError("разбор PDF оборвался в дочернем процессе")
        raise PdfParseTimeoutError(f"разбор PDF превысил {timeout_s:.1f} с")
    finally:
        parent.close()
        _ensure_dead(proc)


async def run_pdf_parse(
    parser: Callable[[bytes], T],
    data: bytes,
    *,
    timeout_s: float = DEFAULT_PDF_PARSE_TIMEOUT_S,
) -> T:
    if timeout_s <= 0:
        raise ValueError("timeout_s должен быть положительным")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(run_pdf_parse_sync, parser, data, timeout_s=timeout_s),
    )
