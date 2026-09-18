"""Защита event loop от зависания PDF-парсера (audit-2026-09).

Донор AeroBIM: PROC-01 — subprocess isolation + RLIMIT_CPU/AS (POSIX)
/ Windows Job Object, закрыт 2026-09-05.

Контур-решение: asyncio.wait_for поверх ThreadPoolExecutor.
Преимущества: чистый Python, кросс-платформенный.
Ограничение: поток продолжает работать после timeout (нет SIGKILL),
но event loop разблокирован — достаточно для Gate L p95 <= 200 ms.
Follow-up PR: subprocess isolation (полный аналог AeroBIM).

Дополнительные переменные среды:
  KONTUR_PDF_PARSE_TIMEOUT_S  -- лимит wall-clock в секундах (default 25.0; 0 = откл)
  KONTUR_PDF_PARSE_WORKERS    -- пул потоков (default 4)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

_T = TypeVar("_T")

_DEFAULT_TIMEOUT_S: float = float(os.environ.get("KONTUR_PDF_PARSE_TIMEOUT_S", "25.0"))
_DEFAULT_WORKERS: int = int(os.environ.get("KONTUR_PDF_PARSE_WORKERS", "4"))

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor  # noqa: PLW0603
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_DEFAULT_WORKERS,
            thread_name_prefix="pdf-guard",
        )
    return _executor


class PdfParseTimeoutError(RuntimeError):
    """Таймаут wall-clock парсера PDF.

    process_id передаётся в лог для диагностики.
    Поток ThreadPoolExecutor продолжает работать; event loop разблокирован.
    """

    def __init__(self, process_id: str, timeout_s: float) -> None:
        super().__init__(
            f"PDF parse timeout after {timeout_s:.1f}s [process_id={process_id!r}]. "
            "Event loop unblocked; background thread may still be running."
        )
        self.process_id = process_id
        self.timeout_s = timeout_s


async def parse_with_timeout(
    fn: Callable[[], _T],
    *,
    timeout_s: float | None = None,
    process_id: str = "",
) -> _T:
    """Запускает fn() в ThreadPoolExecutor с wall-clock timeout.

    timeout_s=0 -- guard отключён (для тестов с быстрыми файлами).
    Если fn() бросает исключение -- оно пробрасывается называющему.
    """
    effective_timeout = timeout_s if timeout_s is not None else _DEFAULT_TIMEOUT_S

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(_get_executor(), fn)

    if effective_timeout == 0:
        return await future

    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout=effective_timeout)
    except asyncio.TimeoutError:
        raise PdfParseTimeoutError(process_id=process_id, timeout_s=effective_timeout)


async def assess_with_timeout(
    data: bytes,
    *,
    timeout_s: float | None = None,
    process_id: str = "",
) -> object:
    """Запускает assess_pdf_bytes(data) с wall-clock timeout.

    Используется вместо прямого вызова assess_pdf_bytes(data)
    всюду, где работает async-контекст (FastAPI handler, background task).
    """
    from kontur.infrastructure.pdfium_visual import assess_pdf_bytes
    return await parse_with_timeout(
        lambda: assess_pdf_bytes(data),
        timeout_s=timeout_s,
        process_id=process_id,
    )
