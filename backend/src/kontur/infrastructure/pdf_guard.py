"""Таймаут разбора PDF без SIGKILL.

Поток в ThreadPool не убивается по истечении wait: это ограничение CPython,
не изоляция процесса (GAP-ISOLATE). Тишина не считается успехом: по таймауту
бросаем PdfParseTimeoutError.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import TypeVar

T = TypeVar("T")

DEFAULT_PDF_PARSE_TIMEOUT_S = 30.0


class PdfParseTimeoutError(TimeoutError):
    """Разбор PDF не уложился в отведённое время."""


def run_pdf_parse_sync(
    parser: Callable[[bytes], T],
    data: bytes,
    *,
    timeout_s: float = DEFAULT_PDF_PARSE_TIMEOUT_S,
) -> T:
    if timeout_s <= 0:
        raise ValueError("timeout_s должен быть положительным")
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kontur-pdf")
    try:
        future = pool.submit(parser, data)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeoutError as exc:
            raise PdfParseTimeoutError(f"разбор PDF превысил {timeout_s:.1f} с") from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


async def run_pdf_parse(
    parser: Callable[[bytes], T],
    data: bytes,
    *,
    timeout_s: float = DEFAULT_PDF_PARSE_TIMEOUT_S,
) -> T:
    if timeout_s <= 0:
        raise ValueError("timeout_s должен быть положительным")
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, parser, data),
            timeout=timeout_s,
        )
    except TimeoutError as exc:
        raise PdfParseTimeoutError(f"разбор PDF превысил {timeout_s:.1f} с") from exc
