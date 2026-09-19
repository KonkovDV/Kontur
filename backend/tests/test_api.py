"""HTTP upload intake: real multipart limits, atomicity, and cleanup."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.presentation import api
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
CORRUPTED = b"PK\x03\x04not-a-pdf"
INSPECTOR = {"Authorization": "Bearer insp-7/INSPECTOR"}


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.state.workspace = ProcessWorkspace()
    with TestClient(app) as test_client:
        yield test_client


def _upload(
    client: TestClient,
    *,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    process_id: str | None = None,
):  # type: ignore[no-untyped-def]
    data = {"object_id": "obj-1", "doc_stage": "PD"}
    if process_id is not None:
        data["process_id"] = process_id
    return client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data=data,
        files=files or [("files", ("pz.pdf", PDF, "application/pdf"))],
    )


def _record_snapshot(record: Any) -> object:
    return copy.deepcopy(
        (
            record.process_state,
            record.files,
            getattr(record, "blobs", {}),
            record.findings,
            record.audit.records,
            record.completeness,
        )
    )


def test_real_multipart_per_file_plus_one_is_413_without_new_process(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api, "MAX_FILE_BYTES", len(PDF) - 1)
    response = _upload(client)
    assert response.status_code == 413
    assert response.json() == {"detail": "request too large"}
    assert app.state.workspace._items == {}  # noqa: SLF001


def test_mixed_valid_and_corrupted_files_are_rejected_atomically(
    client: TestClient,
) -> None:
    response = _upload(
        client,
        files=[
            ("files", ("valid.pdf", PDF, "application/pdf")),
            ("files", ("corrupted.pdf", CORRUPTED, "application/pdf")),
        ],
    )
    assert response.status_code == 422
    assert response.json()["reason_code"] == "CORRUPTED_FILE"
    assert app.state.workspace._items == {}  # noqa: SLF001


@pytest.mark.parametrize("bad_name", ["../../unsafe.pdf", "corrupted.pdf"])
def test_mixed_valid_and_unsafe_or_corrupted_file_never_creates_process(
    client: TestClient, bad_name: str
) -> None:
    bad_body = PDF if "unsafe" in bad_name else CORRUPTED
    response = _upload(
        client,
        files=[
            ("files", ("valid.pdf", PDF, "application/pdf")),
            ("files", (bad_name, bad_body, "application/pdf")),
        ],
    )
    assert response.status_code == 422
    assert app.state.workspace._items == {}  # noqa: SLF001


def test_resumed_mixed_rejection_does_not_mutate_existing_record(
    client: TestClient,
) -> None:
    created = _upload(client)
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    before = _record_snapshot(record)

    rejected = _upload(
        client,
        process_id=process_id,
        files=[
            ("files", ("another.pdf", PDF + b"\n", "application/pdf")),
            ("files", ("corrupted.pdf", CORRUPTED, "application/pdf")),
        ],
    )

    assert rejected.status_code == 422
    same_record = app.state.workspace.get(process_id)
    assert same_record is record
    assert _record_snapshot(record) == before


def test_upload_hash_uses_actual_file_bytes(client: TestClient) -> None:
    response = _upload(client)
    assert response.status_code == 202
    assert response.json()["accepted"][0]["file_hash"] == hashlib.sha256(PDF).hexdigest()


def test_uploads_are_closed_on_success_rejection_and_exception(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: list[str | None] = []
    original_close = UploadFile.close

    async def tracked_close(upload: UploadFile) -> None:
        closed.append(upload.filename)
        await original_close(upload)

    monkeypatch.setattr(UploadFile, "close", tracked_close)

    success = _upload(client)
    assert success.status_code == 202
    assert "pz.pdf" in closed

    closed.clear()
    rejected = _upload(
        client,
        files=[
            ("files", ("valid.pdf", PDF, "application/pdf")),
            ("files", ("corrupted.pdf", CORRUPTED, "application/pdf")),
        ],
    )
    assert rejected.status_code == 422
    assert set(closed) == {"valid.pdf", "corrupted.pdf"}

    closed.clear()

    def fail_pipeline(_record: object) -> None:
        raise RuntimeError("pipeline failed")

    monkeypatch.setattr(app.state.workspace, "run_matrix_pipeline", fail_pipeline)
    with pytest.raises(RuntimeError, match="pipeline failed"):
        _upload(
            client,
            files=[("files", ("exception.pdf", PDF + b"x", "application/pdf"))],
        )
    assert closed == ["exception.pdf"]
