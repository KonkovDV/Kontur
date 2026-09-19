# blob SHA: 66f87cd0190c4f2b40d7e05d41f9fe13dc0eca4a
"""HTTP upload intake: real multipart limits, atomicity, and cleanup."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import DocStage
from kontur.presentation import api
from kontur.presentation.api import app
from kontur.presentation.upload_limits import UploadLimitExceeded

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
CORRUPTED = b"PK\x03\x04not-a-pdf"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


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


class _SecondPassUpload(UploadFile):
    """Return changed bytes or fail after the metadata pass rewinds."""

    def __init__(self, second_body: bytes | None) -> None:
        super().__init__(file=io.BytesIO(PDF), filename="changing.pdf")
        self._first = io.BytesIO(PDF)
        self._second = None if second_body is None else io.BytesIO(second_body)
        self._pass = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pass == 0:
            return self._first.read(size)
        if self._second is None:
            raise OSError("second-pass read failed")
        return self._second.read(size)

    async def seek(self, offset: int) -> None:
        if offset == 0 and self._pass == 0:
            self._pass = 1
        if self._pass == 0:
            self._first.seek(offset)
        elif self._second is not None:
            self._second.seek(offset)


async def _direct_upload(upload: UploadFile, process_id: str | None = None) -> None:
    await api.upload_documents(
        object_id="obj-1",
        files=[upload],
        authorization=INSPECTOR["Authorization"],
        process_id=process_id,
        doc_stage=DocStage.PD,
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


def test_changed_second_pass_leaves_new_workspace_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "1")
    workspace = ProcessWorkspace()
    app.state.workspace = workspace
    pipeline_calls: list[object] = []
    monkeypatch.setattr(
        workspace,
        "run_matrix_pipeline",
        lambda record: pipeline_calls.append(record),
    )

    with pytest.raises(UploadLimitExceeded):
        asyncio.run(_direct_upload(_SecondPassUpload(PDF + b"changed")))

    assert workspace._items == {}  # noqa: SLF001
    assert pipeline_calls == []


def test_read_failure_second_pass_leaves_existing_process_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _upload(client)
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    workspace = app.state.workspace
    record = workspace.get(process_id)
    assert record is not None
    before = _record_snapshot(record)
    before_items = dict(workspace._items)  # noqa: SLF001
    pipeline_calls: list[object] = []
    monkeypatch.setattr(
        workspace,
        "run_matrix_pipeline",
        lambda current: pipeline_calls.append(current),
    )

    with pytest.raises(OSError, match="second-pass read failed"):
        asyncio.run(_direct_upload(_SecondPassUpload(None), process_id))

    assert workspace._items == before_items  # noqa: SLF001
    assert workspace.get(process_id) is record
    assert _record_snapshot(record) == before
    assert pipeline_calls == []



def test_materialize_failure_on_second_file_does_not_create_process(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = api.materialize_upload
    calls = 0

    async def fail_second(
        upload: UploadFile,
        *,
        expected_size: int,
        expected_digest: str,
        max_file_bytes: int,
    ) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("materialize failed")
        return await original(
            upload,
            expected_size=expected_size,
            expected_digest=expected_digest,
            max_file_bytes=max_file_bytes,
        )

    monkeypatch.setattr(api, "materialize_upload", fail_second)

    with pytest.raises(OSError, match="materialize failed"):
        _upload(
            client,
            files=[
                ("files", ("first.pdf", PDF + b"first", "application/pdf")),
                ("files", ("second.pdf", PDF + b"second", "application/pdf")),
            ],
        )

    assert app.state.workspace._items == {}  # noqa: SLF001


def test_materialize_failure_on_second_file_does_not_mutate_resumed_process(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _upload(client)
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    workspace = app.state.workspace
    record = workspace.get(process_id)
    assert record is not None
    before = _record_snapshot(record)
    before_items = dict(workspace._items)  # noqa: SLF001

    original = api.materialize_upload
    calls = 0

    async def fail_second(
        upload: UploadFile,
        *,
        expected_size: int,
        expected_digest: str,
        max_file_bytes: int,
    ) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("materialize failed")
        return await original(
            upload,
            expected_size=expected_size,
            expected_digest=expected_digest,
            max_file_bytes=max_file_bytes,
        )

    monkeypatch.setattr(api, "materialize_upload", fail_second)

    with pytest.raises(OSError, match="materialize failed"):
        _upload(
            client,
            process_id=process_id,
            files=[
                ("files", ("first.pdf", PDF + b"first", "application/pdf")),
                ("files", ("second.pdf", PDF + b"second", "application/pdf")),
            ],
        )

    assert workspace._items == before_items  # noqa: SLF001
    assert workspace.get(process_id) is record
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
