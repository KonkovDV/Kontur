"""Адрес РиН остаётся внутри контура. Пустой адрес — не сдача."""

from __future__ import annotations

from kontur.infrastructure.rin_client import RinStatus, deliver_protocol, is_contour_url


def test_public_http_is_refused() -> None:
    assert is_contour_url("http://127.0.0.1/rin") is False
    assert is_contour_url("https://example.com/rin") is False
    assert is_contour_url("https://127.0.0.1/rin") is True
    assert is_contour_url("https://rin/protocol") is True
    assert is_contour_url("https://rin.corp/protocol", ("rin.corp",)) is True


def test_missing_url_is_local_only() -> None:
    result = deliver_protocol(b"{}", url="", event_id="event-1")
    assert result.status is RinStatus.LOCAL_ONLY
    assert result.retryable is False


def test_public_url_is_not_retried() -> None:
    result = deliver_protocol(b"{}", url="https://example.com/rin", event_id="event-1")
    assert result.status is RinStatus.SEND_REFUSED
    assert result.retryable is False
