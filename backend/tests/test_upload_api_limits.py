"""HTTP upload: mixed intake, file limit, and TZ rejection body."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    with TestClient(app) as test_client:
        yield test_client


def test_mixed_pdf_and_dwg_keeps_accepted_and_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[
            ("files", ("ok.pdf", PDF, "application/pdf")),
            ("files", ("plan.dwg", b"not-dwg", "application/octet-stream")),
        ],
    )
    assert response.status_code == 202
    body = response.json()
    assert len(body["accepted"]) == 1
    assert body["rejected"][0]["reason_code"] == "UNSUPPORTED_FORMAT"
    assert len(app.state.workspace._items) == 1


def test_file_over_limit_is_file_too_large_without_process(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kontur.application.intake.MAX_FILE_BYTES", 8)
    response = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", ("big.pdf", PDF, "application/pdf"))],
    )
    assert response.status_code == 413
    assert response.json()["reason_code"] == "FILE_TOO_LARGE"
    assert app.state.workspace._items == {}
