"""§13 п.4–5: Prometheus /metrics для ядра (CPU/RAM процесса + счётчик загрузок).

Findings/processing-метрики убраны (не были подключены; deferred).
Не ELK и не алерты. Grafana/стек — отдельно (профиль observability, не default).
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from starlette.requests import Request
from starlette.responses import Response

UPLOADS_TOTAL = Counter(
    "kontur_uploads_total",
    "Document upload outcomes",
    ["result"],
    registry=DEFAULT_REGISTRY,
)


def metrics_response(_request: Request) -> Response:
    """Prometheus text exposition (не под /api/v1 — gateway не проксирует)."""

    return Response(content=generate_latest(DEFAULT_REGISTRY), media_type=CONTENT_TYPE_LATEST)


def note_upload(result: str) -> None:
    UPLOADS_TOTAL.labels(result=result).inc()
