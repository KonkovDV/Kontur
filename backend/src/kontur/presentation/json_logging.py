"""§13 п.1: JSON-логи с шестью обязательными полями ТЗ.

Формат одной строки stdout: JSON-объект с ключами
``timestamp``, ``level``, ``service``, ``message``, ``request_id``, ``user_id``.
Это HTTP-observability, не ``audit_log`` (§12) и не ``payload_sha256`` (RiN).
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Final
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

TZ_LOG_FIELDS: Final[tuple[str, ...]] = (
    "timestamp",
    "level",
    "service",
    "message",
    "request_id",
    "user_id",
)

_LEVEL_LABELS: Final[dict[int, str]] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
}

request_id_var: ContextVar[str] = ContextVar("kontur_request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("kontur_user_id", default="anonymous")

_CONFIGURED = False


def _utc_timestamp() -> str:
    # RFC3339 / ISO-8601 UTC with milliseconds
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class TzJsonFormatter(logging.Formatter):
    """Одна строка = JSON с именами полей из ТЗ §13 п.1."""

    def __init__(self, *, service: str = "kontur-core") -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": _utc_timestamp(),
            "level": _LEVEL_LABELS.get(record.levelno, "INFO"),
            "service": str(getattr(record, "service", None) or self._service),
            "message": record.getMessage(),
            "request_id": str(
                getattr(record, "request_id", None) or request_id_var.get() or "-"
            ),
            "user_id": str(
                getattr(record, "user_id", None) or user_id_var.get() or "anonymous"
            ),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        if not hasattr(record, "user_id"):
            record.user_id = user_id_var.get()
        return True


def configure_json_logging(*, service: str = "kontur-core") -> logging.Logger:
    """Подключить JSON-formatter к логгеру ``kontur`` (идемпотентно)."""

    global _CONFIGURED
    logger = logging.getLogger("kontur")
    if _CONFIGURED:
        return logger
    handler = logging.StreamHandler()
    handler.setFormatter(TzJsonFormatter(service=service))
    handler.addFilter(_ContextFilter())
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _CONFIGURED = True
    return logger


def reset_json_logging_for_tests() -> None:
    """Сброс идемпотентного флага — только для pytest."""

    global _CONFIGURED
    _CONFIGURED = False
    logger = logging.getLogger("kontur")
    logger.handlers.clear()


def resolve_user_id(authorization: str | None) -> str:
    """Subject из Bearer, иначе ``anonymous``. Ошибки auth не роняют лог."""

    if not authorization:
        return "anonymous"
    try:
        from kontur.presentation.auth import parse_bearer

        return parse_bearer(authorization).subject or "anonymous"
    except Exception:
        return "anonymous"


class JsonRequestLogMiddleware(BaseHTTPMiddleware):
    """Прокидывает ``X-Request-Id``, пишет access-лог в формате §13 п.1."""

    def __init__(self, app: ASGIApp, *, service: str = "kontur-core") -> None:
        super().__init__(app)
        self._service = service
        self._logger = configure_json_logging(service=service)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get("x-request-id")
        request_id = incoming.strip() if incoming and incoming.strip() else str(uuid4())
        user_id = resolve_user_id(request.headers.get("authorization"))
        tok_r = request_id_var.set(request_id)
        tok_u = user_id_var.set(user_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            self._logger.info(
                "request %s %s",
                request.method,
                request.url.path,
                extra={"service": self._service, "request_id": request_id, "user_id": user_id},
            )
            return response
        finally:
            request_id_var.reset(tok_r)
            user_id_var.reset(tok_u)
