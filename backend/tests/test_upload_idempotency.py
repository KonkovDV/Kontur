"""Regression coverage for hash+stage upload idempotency."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import DocStage
from kontur.domain.statuses import ProcessState
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
NEW_PDF = PDF + b"% second document\n"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    with TestClient(app) as test_client:
        yield test_client


def _upload(
    client: TestClient,
    body: bytes = PDF,
    *,
    stage: str = "PD",
    process_id: str | None = None,
    extra: list[tuple[str, tuple[str, bytes, str]]] | None = None,
):  # type: ignore[no-untyped-def]
    data = {"object_id": "obj-1", "doc_stage": stage}
    if process_id is not None:
        data["process_id"] = process_id
    files = [("files", ("document.pdf", body, "application/pdf"))]
    if extra:
        files.extend(extra)
    return client.post(
        "/api/v1/documents/upload", headers=INSPECTOR, data=data, files=files
    )


def _domain_snapshot(record: Any) -> object:
    return copy.deepcopy(
        (
            record.process_state,
            record.findings,
            record.completeness,
            record.audit.records,
            record.files,
            getattr(record, "blobs", {}),
            record.parse_attempts,
            record.to_status()["counters"],
        )
    )


def test_ten_retries_after_verifying_are_side_effect_free(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _upload(client)
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    opened = client.post(
        f"/api/v1/processes/{process_id}/verify",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert opened.status_code == 200
    assert opened.json()["process_state"] == "VERIFYING"

    record = app.state.workspace.get(process_id)
    assert record is not None
    digest = hashlib.sha256(PDF).hexdigest()
    assert record.has_file(digest, DocStage.PD)
    assert app.state.workspace.has_file(record, digest, DocStage.PD)
    before = _domain_snapshot(record)
    parser_calls = 0

    def forbidden_parser(*_args: object, **_kwargs: object) -> None:
        nonlocal parser_calls
        parser_calls += 1
        raise AssertionError("duplicate retry reached parser/pipeline")

    monkeypatch.setattr(
        "kontur.application.runtime.run_process_pipeline", forbidden_parser
    )
    for _ in range(10):
        retried = _upload(client, process_id=process_id)
        assert retried.status_code == 202
        assert retried.json() == {
            "process_id": process_id,
            "accepted": [],
            "rejected": [],
        }

    assert parser_calls == 0
    assert _domain_snapshot(record) == before


def test_mixed_batch_processes_only_new_file(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _upload(client)
    process_id = created.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    files_before = len(record.files)
    blobs_before = len(getattr(record, "blobs", {}))
    calls = 0
    original = app.state.workspace.run_matrix_pipeline

    def counted(current: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(current)

    monkeypatch.setattr(app.state.workspace, "run_matrix_pipeline", counted)
    response = _upload(
        client,
        process_id=process_id,
        extra=[("files", ("new.pdf", NEW_PDF, "application/pdf"))],
    )
    assert response.status_code == 202
    assert len(response.json()["accepted"]) == 1
    assert response.json()["accepted"][0]["file_hash"] == hashlib.sha256(
        NEW_PDF
    ).hexdigest()
    assert response.json()["rejected"] == []
    assert calls == 1
    assert len(record.files) == files_before + 1
    assert len(getattr(record, "blobs", {})) == blobs_before + 1


def test_same_bytes_in_different_stage_are_new(client: TestClient) -> None:
    created = _upload(client)
    process_id = created.json()["process_id"]
    response = _upload(client, stage="RD", process_id=process_id)
    assert response.status_code == 202
    assert len(response.json()["accepted"]) == 1
    record = app.state.workspace.get(process_id)
    assert record is not None
    digest = hashlib.sha256(PDF).hexdigest()
    assert record.has_file(digest, DocStage.PD)
    assert record.has_file(digest, DocStage.RD)
    assert len(record.files) == 2


def test_finalized_duplicate_remains_conflict(client: TestClient) -> None:
    created = _upload(client)
    process_id = created.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    record.process_state = ProcessState.FINALIZED

    response = _upload(client, process_id=process_id)
    assert response.status_code == 409
    assert record.process_state is ProcessState.FINALIZED
    assert len(record.files) == 1
