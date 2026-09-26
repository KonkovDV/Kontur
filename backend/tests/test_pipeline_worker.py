"""Загрузка отвечает до конца L1–L7. Чтение процесса ждёт поток API."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessRecord, ProcessWorkspace
from kontur.domain.statuses import FindingStatus, ProcessState
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    with TestClient(app) as test_client:
        yield test_client


def _upload(client: TestClient):
    return client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )


def test_upload_returns_while_pipeline_is_still_parsing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    original = ProcessWorkspace.run_matrix_pipeline

    def gated(self: ProcessWorkspace, record: ProcessRecord) -> object:
        started.set()
        if not release.wait(3):
            raise AssertionError("прогон не отпустили")
        return original(self, record)

    monkeypatch.setattr(ProcessWorkspace, "run_matrix_pipeline", gated)
    response = _upload(client)
    assert response.status_code == 202
    assert started.wait(2)
    process_id = response.json()["process_id"]
    pending = app.state.workspace.peek(process_id)
    assert pending is not None
    assert pending.process_state is ProcessState.PARSING
    release.set()
    ready = app.state.workspace.get(process_id)
    assert ready is not None
    assert ready.process_state is ProcessState.READY
    assert ready.findings
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in ready.findings.values()
    )


def test_pipeline_failure_unblocks_readers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: ProcessWorkspace, record: object) -> object:
        del self, record
        raise RuntimeError("parse")

    monkeypatch.setattr(ProcessWorkspace, "run_matrix_pipeline", boom)
    response = _upload(client)
    assert response.status_code == 202
    process_id = response.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    assert record.process_state is ProcessState.PARSING
    failed = [action for _actor, action, _payload in record.audit.records]
    assert "PIPELINE_FAILED" in failed
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in record.findings.values()
    )
