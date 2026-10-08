"""Проверка clamd INSTREAM до того, как файл попадёт в комплект.

Если адрес антивируса не задан, приём в контуре разработки не притворяется
проверкой: статус NOT_CONFIGURED. Если адрес задан или проверка обязательна,
а демон молчит, файл не принимается.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

_CHUNK = 1 << 16
_TIMEOUT_S = 60.0


class AvStatus(StrEnum):
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class _Stream(Protocol):
    def sendall(self, data: bytes) -> None: ...

    def recv(self, size: int) -> bytes: ...

    def close(self) -> None: ...


def parse_clamd_reply(text: str) -> tuple[AvStatus, str]:
    """Ответ демона: `stream: OK` или `stream: Eicar FOUND`."""

    cleaned = text.replace("\0", "").strip()
    if cleaned.endswith("OK"):
        return AvStatus.CLEAN, ""
    if cleaned.endswith("FOUND"):
        detail = cleaned.split(":", 1)[-1].strip()
        return AvStatus.INFECTED, detail or "FOUND"
    if not cleaned:
        return AvStatus.UNAVAILABLE, "антивирус не ответил"
    return AvStatus.UNAVAILABLE, f"неожиданный ответ антивируса: {cleaned[:200]}"


def scan_instream(
    payload: bytes,
    opener: Callable[[], _Stream],
) -> tuple[AvStatus, str]:
    """Отправить байты командой zINSTREAM и разобрать одну строку ответа."""

    stream = opener()
    try:
        stream.sendall(b"zINSTREAM\0")
        for start in range(0, len(payload), _CHUNK):
            piece = payload[start : start + _CHUNK]
            stream.sendall(len(piece).to_bytes(4, "big") + piece)
        stream.sendall((0).to_bytes(4, "big"))
        chunks: list[bytes] = []
        while True:
            part = stream.recv(4096)
            if not part:
                break
            chunks.append(part)
    except OSError as exc:
        return AvStatus.UNAVAILABLE, f"антивирус недоступен: {exc.__class__.__name__}"
    finally:
        stream.close()
    return parse_clamd_reply(b"".join(chunks).decode("utf-8", errors="replace"))


def _tcp_opener(host: str, port: int) -> Callable[[], _Stream]:
    def open_stream() -> _Stream:
        sock = socket.create_connection((host, port), timeout=_TIMEOUT_S)
        sock.settimeout(_TIMEOUT_S)
        return sock

    return open_stream


def scan_bytes(
    payload: bytes,
    *,
    host: str = "",
    port: int = 3310,
    required: bool = False,
    opener: Callable[[], _Stream] | None = None,
) -> tuple[AvStatus, str]:
    """Проверить файл. Без адреса и без обязательности проверка не имитируется."""

    if not host:
        if required:
            return AvStatus.UNAVAILABLE, "антивирус контура не подключён"
        return AvStatus.NOT_CONFIGURED, "антивирус контура не подключён"
    try:
        return scan_instream(payload, opener or _tcp_opener(host, port))
    except OSError as exc:
        return AvStatus.UNAVAILABLE, f"антивирус недоступен: {exc.__class__.__name__}"


def scan_from_env(payload: bytes) -> tuple[AvStatus, str]:
    host = os.environ.get("KONTUR_CLAMD_HOST", "").strip()
    raw_port = os.environ.get("KONTUR_CLAMD_PORT", "3310").strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = 3310
    required = os.environ.get("KONTUR_CLAMD_REQUIRED", "").strip().lower() == "true"
    return scan_bytes(payload, host=host, port=port, required=required)
