"""Передача финализированного протокола в ИАИС «РиН».

Адрес не задан — пакет остаётся LOCAL_ONLY, это не успешная сдача.
Приёмник только по HTTPS внутри контура. Клиентский сертификат — УКЭП
на TLS 1.3; криптография ГОСТ остаётся у СКЗИ заказчика перед приёмником.
Повторы 1/5/15 минут делает outbox, этот модуль только классифицирует ответ.
"""

from __future__ import annotations

import ipaddress
import os
import ssl
from dataclasses import dataclass
from enum import StrEnum
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class RinStatus(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    SENT = "SENT"
    SEND_FAILED = "SEND_FAILED"
    SEND_REFUSED = "SEND_REFUSED"


@dataclass(frozen=True, slots=True)
class RinResult:
    status: RinStatus
    detail: str
    retryable: bool


def _private_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    if isinstance(address, ipaddress.IPv4Address):
        return bool(
            address.is_private or address.is_loopback or address.is_link_local
        )
    return bool(address.is_loopback or address.is_private or address.is_link_local)


def is_contour_url(url: str, allowed_hosts: tuple[str, ...] = ()) -> bool:
    """HTTPS и хост внутри контура. Публичный адрес с точкой снаружи не проходит."""

    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {item.lower() for item in allowed_hosts}:
        return True
    return _private_host(host)


def _ssl_context(certfile: str, keyfile: str, cafile: str) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=cafile or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    if certfile and keyfile:
        context.load_cert_chain(certfile, keyfile)
    return context


def deliver_protocol(
    body: bytes,
    *,
    url: str = "",
    event_id: str,
    certfile: str = "",
    keyfile: str = "",
    cafile: str = "",
    allowed_hosts: tuple[str, ...] = (),
    opener: object | None = None,
) -> RinResult:
    """Отправить протокол. `opener` подменяет сеть в тесте."""

    if not url.strip():
        return RinResult(
            RinStatus.LOCAL_ONLY,
            "передача не включена: адрес приёма не задан",
            False,
        )
    if not is_contour_url(url, allowed_hosts):
        return RinResult(
            RinStatus.SEND_REFUSED,
            "адрес приёма должен быть HTTPS внутри контура",
            False,
        )
    request = Request(  # noqa: S310
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": event_id,
        },
        method="POST",
    )
    open_url = opener or urlopen
    try:
        context = _ssl_context(certfile, keyfile, cafile)
        with open_url(request, context=context, timeout=30) as response:  # type: ignore[operator]
            status = getattr(response, "status", 200)
    except HTTPError as exc:
        return RinResult(
            RinStatus.SEND_FAILED,
            f"приёмник отказал: HTTP {exc.code}",
            exc.code >= 500,
        )
    except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
        return RinResult(
            RinStatus.SEND_FAILED,
            f"приёмник недоступен: {exc.__class__.__name__}",
            True,
        )
    if status >= 500:
        return RinResult(RinStatus.SEND_FAILED, f"приёмник отказал: HTTP {status}", True)
    if status >= 400:
        return RinResult(RinStatus.SEND_FAILED, f"приёмник отказал: HTTP {status}", False)
    return RinResult(RinStatus.SENT, f"принято приёмником: HTTP {status}", False)


def deliver_from_env(body: bytes, *, event_id: str) -> RinResult:
    allowed = tuple(
        item.strip()
        for item in os.environ.get("KONTUR_RIN_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )
    return deliver_protocol(
        body,
        url=os.environ.get("KONTUR_RIN_URL", "").strip(),
        event_id=event_id,
        certfile=os.environ.get("KONTUR_RIN_CERT", "").strip(),
        keyfile=os.environ.get("KONTUR_RIN_KEY", "").strip(),
        cafile=os.environ.get("KONTUR_RIN_CA", "").strip(),
        allowed_hosts=allowed,
    )
