"""PDF parse timeout guard (donor: AeroBIM pdfium_isolate wall-clock kill).

AeroBIM runs PDF parsing in a child process with RLIMIT_CPU=30s (POSIX) or
a Windows Job Object (PROC-01, closed 2026-09-05). Kontur runs in a single
process via FastAPI BackgroundTasks, so we use asyncio.wait_for over
run_in_executor instead of a child process.

This is a lighter-weight guard: it does NOT cap RSS (no RLIMIT_AS) but it
DOES prevent a single large PDF from blocking the event loop and causing
Gate L p95 ≤200ms to fail at 100 VU.

Usage:
    from kontur.infrastructure.pdf_timeout import parse_with_timeout

    tokens = await parse_with_timeout(
        lambda: extract_tokens(path),
        timeout_s=25.0,
        process_id=record.process_id,
    )

Raises PdfParseTimeoutError if the parse exceeds timeout_s seconds.

KONTUR_PDF_PARSE_TIMEOUT_S env var overrides the default (25.0 s).
Set to 0 to disable (tests / local dev only).
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_DEFAULT_TIMEOUT_S = 25.0
_ENV_KEY = "KONTUR_PDF_PARSE_TIMEOUT_S"

# Shared executor: bounded thread pool for PDF parsing.
# Keeps GIL release predictable and avoids unlimited thread spawning.
_PDF_EXECUTOR = ThreadPoolExecutor(
    max_workers=int(os.environ.get("KONTUR_PDF_PARSE_WORKERS", "4")),
    thread_name_prefix="kontur-pdf-parse",
)


class PdfParseTimeoutError(RuntimeError):
    """Raised when PDF parsing exceeds the configured wall-clock timeout."""

    def __init__(self, process_id: str, timeout_s: float) -> None:
        super().__init__(
            f"[process_id={process_id}] PDF parsing exceeded wall-clock timeout "
            f"of {timeout_s:.1f}s — gate L guard triggered. "
            "Consider splitting the PDF or raising KONTUR_PDF_PARSE_TIMEOUT_S."
        )
        self.process_id = process_id
        self.timeout_s = timeout_s


def _configured_timeout() -> float:
    """Read KONTUR_PDF_PARSE_TIMEOUT_S from env; fall back to default."""
    raw = os.environ.get(_ENV_KEY)
    if raw is None:
        return _DEFAULT_TIMEOUT_S
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_S


async def parse_with_timeout(
    sync_callable: Callable[[], T],
    *,
    timeout_s: float | None = None,
    process_id: str = "unknown",
) -> T:
    """Run sync_callable in a thread and kill it if it exceeds timeout_s.

    Args:
        sync_callable: A synchronous callable (e.g. lambda: pdfium.extract(path)).
        timeout_s: Wall-clock timeout in seconds. None → KONTUR_PDF_PARSE_TIMEOUT_S
                   env var or 25.0 s default. 0 → no timeout (dev/test only).
        process_id: For error message traceability in logs.

    Returns:
        The return value of sync_callable.

    Raises:
        PdfParseTimeoutError: If the parse exceeds timeout_s seconds.
        Any exception raised by sync_callable is propagated as-is.
    """
    effective_timeout = timeout_s if timeout_s is not None else _configured_timeout()

    loop = asyncio.get_event_loop()
    future = loop.run_in_executor(_PDF_EXECUTOR, sync_callable)

    if effective_timeout <= 0:
        # Timeout disabled: dev/test shortcut.
        return await future

    try:
        return await asyncio.wait_for(asyncio.shield(future), timeout=effective_timeout)
    except asyncio.TimeoutError:
        # Note: the thread continues running (no POSIX SIGKILL here).
        # A follow-up PR can add OS-level kill via subprocess isolation.
        # For Gate L this is sufficient: the event loop is unblocked.
        raise PdfParseTimeoutError(process_id=process_id, timeout_s=effective_timeout)
