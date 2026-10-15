"""§13 п.4–5: Prometheus /metrics ядра (не путать с evaluation test_metrics.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.presentation.api import app
from kontur.presentation.prometheus_metrics import note_upload


def test_metrics_endpoint_exposes_process_and_domain_counters() -> None:
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    note_upload("accepted")
    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "process_resident_memory_bytes" in body or "process_virtual_memory_bytes" in body
    assert "kontur_uploads_total" in body
    assert 'result="accepted"' in body


def test_metrics_not_under_api_v1() -> None:
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    # Публичный префикс не отдаёт exposition (404), чтобы gateway не утекал наружу.
    response = client.get("/api/v1/metrics")
    assert response.status_code == 404
