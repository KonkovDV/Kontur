"""Учебный комплект по HTTP: только при флаге стенда, без автоназначения эталона."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pdf_fixtures import contest_slice_font

from kontur.domain.statuses import FindingStatus
from kontur.presentation.api import app

_FONT = contest_slice_font()
needs_font = pytest.mark.skipif(_FONT is None, reason="нет TTF с кириллицей")
TOKEN = {"Authorization": "Bearer inspector-1@OBJ-DEMO-COLD-START/INSPECTOR"}


def test_demo_kit_is_hidden_without_the_stand_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", raising=False)
    from kontur.application.runtime import ProcessWorkspace

    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    response = client.post("/api/v1/demo/kit", headers=TOKEN)
    assert response.status_code == 404
    assert response.json()["detail"] == "учебный комплект выключен"


@needs_font
def test_demo_kit_loads_four_files_and_leaves_etalon_to_the_inspector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    from kontur.application.runtime import ProcessWorkspace

    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    loaded = client.post("/api/v1/demo/kit", headers=TOKEN)
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["etalon_file_id"] == "f-pd"
    assert body["draft_file_id"] == "f-pd-draft"
    process_id = body["process_id"]

    documents = client.get(f"/api/v1/processes/{process_id}/documents", headers=TOKEN)
    assert documents.status_code == 200
    rows = documents.json()["documents"]
    by_id = {item["file_id"]: item for item in rows}
    assert set(by_id) == {"f-pd-draft", "f-pd", "f-rd", "f-id"}
    assert by_id["f-pd"]["doc_stage"] == "PD"
    assert by_id["f-pd"]["approval_basis"] != "INSPECTOR_SELECT"
    assert by_id["f-id"]["doc_stage"] == "ID"

    findings = client.get(f"/api/v1/processes/{process_id}/findings", headers=TOKEN)
    assert findings.status_code == 200
    listed = findings.json()["findings"]
    assert FindingStatus.CONFIRMED_VIOLATION.value not in {
        item["finding_status"] for item in listed
    }
    pz = next(item for item in listed if item["rule_code"] == "PZ-001")
    assert pz["finding_status"] == "CLARIFICATION_REQUIRED"
