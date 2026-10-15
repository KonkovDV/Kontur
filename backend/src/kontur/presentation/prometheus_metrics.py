"""§13 п.4–5: Prometheus /metrics для ядра (CPU/RAM процесса + доменные счётчики).

Не ELK и не алерты. Grafana/стек — отдельно (профиль observability, не default).
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from starlette.requests import Request
from starlette.responses import Response

UPLOADS_TOTAL = Counter(
    "kontur_uploads_total",
    "Document upload outcomes",
    ["result"],
    registry=DEFAULT_REGISTRY,
)

FINDINGS_TOTAL = Counter(
    "kontur_findings_total",
    "Findings observed by status at scrape-friendly increments",
    ["status"],
    registry=DEFAULT_REGISTRY,
)

PROCESSING_SECONDS = Histogram(
    "kontur_processing_seconds",
    "Processing phase durations in seconds",
    ["phase"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0),
    registry=DEFAULT_REGISTRY,
)


def metrics_response(_request: Request) -> Response:
    """Prometheus text exposition (не под /api/v1 — gateway не проксирует)."""

    return Response(content=generate_latest(DEFAULT_REGISTRY), media_type=CONTENT_TYPE_LATEST)


def note_upload(result: str) -> None:
    UPLOADS_TOTAL.labels(result=result).inc()


def note_finding_status(status: str) -> None:
    FINDINGS_TOTAL.labels(status=status).inc()


def note_processing(phase: str, seconds: float) -> None:
    if seconds < 0:
        return
    PROCESSING_SECONDS.labels(phase=phase).observe(seconds)
