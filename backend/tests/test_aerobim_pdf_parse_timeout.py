"""Tests: PDF parse timeout guard (donor: AeroBIM pdfium_isolate).

Gate L: p95 ≤200ms at 100 VU. A blocked event loop fails this gate.
These tests verify the asyncio.wait_for guard works correctly.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from kontur.infrastructure.pdf_timeout import (
    PdfParseTimeoutError,
    parse_with_timeout,
)


class TestParseWithTimeout:
    """Unit tests for parse_with_timeout coroutine."""

    @pytest.mark.asyncio
    async def test_fast_parse_returns_result(self) -> None:
        result = await parse_with_timeout(
            lambda: "tokens",
            timeout_s=5.0,
            process_id="test-001",
        )
        assert result == "tokens"

    @pytest.mark.asyncio
    async def test_slow_parse_raises_timeout_error(self) -> None:
        def slow_parse() -> str:
            time.sleep(10)  # simulate hung PDF parser
            return "should not reach here"

        with pytest.raises(PdfParseTimeoutError) as exc_info:
            await parse_with_timeout(
                slow_parse,
                timeout_s=0.05,   # 50ms → triggers immediately
                process_id="test-002",
            )

        err = exc_info.value
        assert err.process_id == "test-002"
        assert err.timeout_s == pytest.approx(0.05)
        assert "test-002" in str(err)
        assert "gate L" in str(err).lower() or "gate" in str(err).lower()

    @pytest.mark.asyncio
    async def test_timeout_zero_disables_guard(self) -> None:
        # timeout_s=0 → no limit, returns normally
        result = await parse_with_timeout(
            lambda: 42,
            timeout_s=0,
            process_id="test-003",
        )
        assert result == 42

    @pytest.mark.asyncio
    async def test_exception_from_callable_propagates(self) -> None:
        def failing_parse() -> str:
            raise ValueError("corrupt PDF header")

        with pytest.raises(ValueError, match="corrupt PDF"):
            await parse_with_timeout(
                failing_parse,
                timeout_s=5.0,
                process_id="test-004",
            )

    @pytest.mark.asyncio
    async def test_error_message_contains_process_id(self) -> None:
        process_id = "proc-xyz-789"
        with pytest.raises(PdfParseTimeoutError) as exc_info:
            await parse_with_timeout(
                lambda: time.sleep(10),
                timeout_s=0.05,
                process_id=process_id,
            )
        assert process_id in str(exc_info.value)
