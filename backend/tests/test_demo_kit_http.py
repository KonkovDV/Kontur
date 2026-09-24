"""Учебный комплект по HTTP: только при флаге стенда, без автоназначения эталона."""

from __future__ import annotations

import json

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


def _review(
    client: TestClient,
    finding_id: str,
    action: str,
    comment: str,
    reason_code: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "action": action,
        "inspector_id": "inspector-1",
        "comment": comment,
    }
    if reason_code is not None:
        body["reason_code"] = reason_code
    response = client.post(
        f"/api/v1/findings/{finding_id}/review",
        headers=TOKEN,
        json=body,
    )
    assert response.status_code == 200, response.text
    payload: dict[str, object] = response.json()
    return payload


@needs_font
def test_demo_kit_review_finalize_and_queue_rin_without_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Д2.5: эталон, два подтверждения, один отказ, протокол, очередь без ACK."""

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    from kontur.application.runtime import ProcessWorkspace

    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    loaded = client.post("/api/v1/demo/kit", headers=TOKEN)
    assert loaded.status_code == 200
    process_id = loaded.json()["process_id"]

    early = client.post(f"/api/v1/inspection/{process_id}", headers=TOKEN)
    assert early.status_code == 409

    selected = client.post(
        f"/api/v1/processes/{process_id}/revisions/f-pd/select",
        headers=TOKEN,
        json={
            "inspector_id": "inspector-1",
            "comment": "эталон — лист со штампом Утвердил",
        },
    )
    assert selected.status_code == 200

    listed = client.get(
        f"/api/v1/processes/{process_id}/findings", headers=TOKEN
    ).json()["findings"]
    by_rule = {item["rule_code"]: item for item in listed}
    open_codes = {
        item["rule_code"]
        for item in listed
        if item["finding_status"] in {"CANDIDATE", "SUSPICION"}
    }
    assert open_codes == {"PZ-001", "KR-055", "AR-041"}

    confirmed_area = _review(
        client,
        str(by_rule["PZ-001"]["finding_id"]),
        "CONFIRM",
        "площадь РД меньше утверждённой ПД",
    )
    assert confirmed_area["finding_status"] == "CONFIRMED_VIOLATION"
    confirmed_concrete = _review(
        client,
        str(by_rule["KR-055"]["finding_id"]),
        "CONFIRM",
        "класс бетона РД не совпал с ПД",
    )
    assert confirmed_concrete["finding_status"] == "CONFIRMED_VIOLATION"
    rejected = _review(
        client,
        str(by_rule["AR-041"]["finding_id"]),
        "REJECT",
        "ширина проема согласована отдельным листом",
        "APPROVED_CHANGE_EXISTS",
    )
    assert rejected["finding_status"] == "NEGATIVE_VERIFIED"

    completed = client.post(
        f"/api/v1/processes/{process_id}/complete",
        headers=TOKEN,
        json={"inspector_id": "inspector-1"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["process_state"] == "COMPLETED"
    assert completed.json()["counters"]["candidates"] == 0
    assert completed.json()["counters"]["confirmed_violations"] == 2

    finalized = client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=TOKEN,
        json={"inspector_id": "inspector-1"},
    )
    assert finalized.status_code == 200
    assert finalized.json()["process_state"] == "FINALIZED"
    assert finalized.json()["sync_state"] == "NOT_REQUESTED"

    protocol = client.get(f"/api/v1/processes/{process_id}/protocol", headers=TOKEN)
    assert protocol.status_code == 200
    body = protocol.json()
    dumped = json.dumps(body, ensure_ascii=False)
    assert "AUTO_NO_DIFFERENCE" not in dumped
    assert body["violation_count"] == 2

    journal = client.get(f"/api/v1/processes/{process_id}/audit", headers=TOKEN)
    assert journal.status_code == 200
    actions = [event["action"] for event in journal.json()["events"]]
    assert actions.count("REVIEW") == 3
    assert "COMPLETE_VERIFICATION" in actions
    assert "FINALIZE" in actions

    queued = client.post(f"/api/v1/inspection/{process_id}", headers=TOKEN)
    assert queued.status_code == 202
    assert queued.json() == "PENDING_SYNC"
    status = client.get(f"/api/v1/processes/{process_id}/status", headers=TOKEN)
    assert status.status_code == 200
    assert status.json()["sync_state"] == "PENDING_SYNC"
    again = client.post(f"/api/v1/inspection/{process_id}", headers=TOKEN)
    assert again.status_code == 202
    assert again.json() != "SYNCED"
