"""Четыре монотонных часа на статусе: загрузка, разбор, сравнение, протокол."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kontur.application.process_pipeline import PipelineReport
from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    with TestClient(app) as test_client:
        yield test_client


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def test_status_keeps_upload_parse_compare_and_protocol_apart(client: TestClient) -> None:
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert uploaded.status_code == 202
    process_id = uploaded.json()["process_id"]
    status = client.get(f"/api/v1/processes/{process_id}/status", headers=INSPECTOR)
    assert status.status_code == 200
    before = status.json()["phase_seconds"]
    assert list(before) == ["upload", "parse", "compare"]
    assert before["upload"] >= 0
    assert before["parse"] >= 0
    assert before["compare"] >= 0

    protocol = client.get(f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR)
    assert protocol.status_code == 200
    after = client.get(f"/api/v1/processes/{process_id}/status", headers=INSPECTOR)
    clocks = after.json()["phase_seconds"]
    assert list(clocks) == ["upload", "parse", "compare", "protocol"]
    assert clocks["upload"] == before["upload"]
    assert clocks["parse"] == before["parse"]
    assert clocks["compare"] == before["compare"]
    assert clocks["protocol"] >= 0

    record = app.state.workspace.get(process_id)
    assert record is not None
    pipeline = [
        payload
        for _actor, action, payload in record.audit.records
        if action == "PIPELINE"
    ]
    assert pipeline[-1]["phase_seconds"]["upload"] == before["upload"]
    assert "protocol" not in pipeline[-1]["phase_seconds"]
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in record.findings.values()
    )


def test_repeat_of_the_same_file_does_not_replace_the_upload_clock(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    process_id = first.json()["process_id"]
    before = client.get(
        f"/api/v1/processes/{process_id}/status", headers=INSPECTOR
    ).json()["phase_seconds"]["upload"]
    again = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD", "process_id": process_id},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert again.status_code == 202
    after = client.get(
        f"/api/v1/processes/{process_id}/status", headers=INSPECTOR
    ).json()["phase_seconds"]["upload"]
    assert after == before


def test_pipeline_clocks_do_not_erase_upload_or_accept_other_phases() -> None:
    workspace = ProcessWorkspace()
    record = workspace.create("obj-clock", _completeness())
    workspace.note_phase(record, "upload", 0.25)
    workspace.note_phase(record, "protocol", 0.5)
    kept = workspace._merge_pipeline_clocks(
        record,
        PipelineReport(
            findings=(),
            rules_evaluated=0,
            parse_errors=(),
            pages_built=0,
            stamp_by_file_id={},
            phase_seconds={"parse": 1.5, "compare": 2.5},
        ),
    )
    assert kept == {"upload": 0.25, "parse": 1.5, "compare": 2.5, "protocol": 0.5}
    with pytest.raises(ValueError, match="только пайплайн"):
        workspace.note_phase(record, "parse", 1.0)
    with pytest.raises(ValueError, match="отрицательн"):
        workspace.note_phase(record, "upload", -0.1)
    with pytest.raises(ValueError, match="только разбор"):
        workspace._merge_pipeline_clocks(
            record,
            PipelineReport(
                findings=(),
                rules_evaluated=0,
                parse_errors=(),
                pages_built=0,
                stamp_by_file_id={},
                phase_seconds={"upload": 9.0, "parse": 1.0, "compare": 1.0},
            ),
        )
    assert record.phase_seconds["upload"] == 0.25
    assert record.to_status()["phase_seconds"]["protocol"] == 0.5
