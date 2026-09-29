"""Повтор hash+stage не reopen и не гоняет pipeline."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.statuses import ProcessState
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PDF_B = b"%PDF-1.7\n2 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    with TestClient(app) as test_client:
        yield test_client


def _upload(
    client: TestClient,
    *,
    process_id: str | None = None,
    stage: str = "PD",
    body: bytes = PDF,
    name: str = "pz.pdf",
):
    data = {"object_id": "obj-1", "doc_stage": stage}
    if process_id is not None:
        data["process_id"] = process_id
    return client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data=data,
        files=[("files", (name, body, "application/pdf"))],
    )


def test_duplicate_retry_from_verifying_does_not_rerun_pipeline(
    client: TestClient,
) -> None:
    created = _upload(client)
    process_id = created.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    client.post(
        f"/api/v1/processes/{process_id}/verify",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    record = app.state.workspace.get(process_id)
    assert record is not None
    assert record.process_state is ProcessState.VERIFYING
    snapshot = (
        record.process_state,
        record.parse_attempts,
        len(record.files),
        tuple(item.file_id for item in record.files),
        tuple(record.blobs.keys()),
        tuple(record.audit.records),
        dict(record.completeness),
        len(record.findings),
    )
    for _ in range(10):
        retry = _upload(client, process_id=process_id)
        assert retry.status_code == 202
        assert retry.json()["accepted"] == []
        assert retry.json()["process_id"] == process_id
    after = app.state.workspace.get(process_id)
    assert after is not None
    assert after.process_state is ProcessState.VERIFYING
    assert (
        after.process_state,
        after.parse_attempts,
        len(after.files),
        tuple(item.file_id for item in after.files),
        tuple(after.blobs.keys()),
        tuple(after.audit.records),
        dict(after.completeness),
        len(after.findings),
    ) == snapshot


def test_mixed_duplicate_and_new_file_runs_pipeline_once(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    attempts = record.parse_attempts
    response = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD", "process_id": process_id},
        files=[
            ("files", ("pz.pdf", PDF, "application/pdf")),
            ("files", ("extra.pdf", PDF_B, "application/pdf")),
        ],
    )
    assert response.status_code == 202
    body = response.json()
    assert len(body["accepted"]) == 1
    after = app.state.workspace.get(process_id)
    assert after is not None
    assert len(after.files) == 2
    assert after.parse_attempts == attempts + 1
    assert after.process_state is ProcessState.READY


def test_same_bytes_other_stage_are_new(client: TestClient) -> None:
    process_id = _upload(client, stage="PD").json()["process_id"]
    response = _upload(client, process_id=process_id, stage="RD", name="rd.pdf")
    assert response.status_code == 202
    assert len(response.json()["accepted"]) == 1
    record = app.state.workspace.get(process_id)
    assert record is not None
    assert len(record.files) == 2


def test_completed_duplicate_does_not_reopen(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    record.process_state = ProcessState.COMPLETED
    attempts = record.parse_attempts
    retry = _upload(client, process_id=process_id)
    assert retry.status_code == 202
    assert retry.json()["accepted"] == []
    after = app.state.workspace.get(process_id)
    assert after is not None
    assert after.process_state is ProcessState.COMPLETED
    assert after.parse_attempts == attempts


def test_four_stage_uploads_fit_the_parse_budget(client: TestClient) -> None:
    created = _upload(client)
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    third = b"%PDF-1.7\n3 0 obj\n<<>>\nendobj\n"
    fourth = b"%PDF-1.7\n4 0 obj\n<<>>\nendobj\n"
    assert (
        _upload(client, process_id=process_id, stage="RD", name="rd.pdf", body=PDF_B).status_code
        == 202
    )
    assert (
        _upload(client, process_id=process_id, stage="ID", name="id.pdf", body=third).status_code
        == 202
    )
    assert (
        _upload(client, process_id=process_id, stage="PD", name="pd-2.pdf", body=fourth).status_code
        == 202
    )
    record = app.state.workspace.get(process_id)
    assert record is not None
    assert record.parse_attempts == 4


def test_finalized_duplicate_remains_409(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    record.process_state = ProcessState.FINALIZED
    retry = _upload(client, process_id=process_id)
    assert retry.status_code == 409
