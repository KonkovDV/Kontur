"""§9.3 / топ-20 #12: HTTP-инварианты finalize / unfinalize / status-lock."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus, ProcessState, ReviewPriority
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PDF_NEW = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog>>\nendobj\ntrailer\n"

INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}
SUPERVISOR = {"Authorization": "Bearer sup-1@obj-1/SUPERVISOR"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.setenv("KONTUR_ENV", "dev")
    app.state.workspace = ProcessWorkspace()
    return TestClient(app)


def _upload(client: TestClient, *, name: str = "pz.pdf", content: bytes = PDF):
    return client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", (name, content, "application/pdf"))],
    )


def _seed_completed(client: TestClient) -> str:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    record.process_state = ProcessState.COMPLETED
    return process_id


def _finalize(client: TestClient, process_id: str) -> None:
    response = client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["process_state"] == "FINALIZED"


def test_upload_after_real_finalize_is_409(client: TestClient) -> None:
    process_id = _seed_completed(client)
    _finalize(client, process_id)
    refused = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD", "process_id": process_id},
        files=[("files", ("extra.pdf", PDF_NEW, "application/pdf"))],
    )
    assert refused.status_code == 409
    assert "дозагрузка" in refused.json()["detail"].lower() or "финализ" in refused.json()[
        "detail"
    ].lower()
    # новый хеш — не идемпотентный дубль
    assert hashlib.sha256(PDF_NEW).hexdigest() != hashlib.sha256(PDF).hexdigest()


def test_unfinalize_missing_or_empty_reason_is_422(client: TestClient) -> None:
    process_id = _seed_completed(client)
    _finalize(client, process_id)
    missing = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=SUPERVISOR,
        json={"inspector_id": "sup-1"},
    )
    assert missing.status_code == 422
    empty = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=SUPERVISOR,
        json={"inspector_id": "sup-1", "reason": ""},
    )
    assert empty.status_code == 422
    whitespace = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=SUPERVISOR,
        json={"inspector_id": "sup-1", "reason": "   "},
    )
    assert whitespace.status_code == 422


def test_unfinalize_writes_audit_via_http(client: TestClient) -> None:
    process_id = _seed_completed(client)
    _finalize(client, process_id)
    reason = "ошибка редакции протокола"
    undone = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=SUPERVISOR,
        json={"inspector_id": "sup-1", "reason": reason},
    )
    assert undone.status_code == 200
    assert undone.json()["process_state"] == "COMPLETED"
    audit = client.get(f"/api/v1/processes/{process_id}/audit", headers=INSPECTOR)
    assert audit.status_code == 200
    events = audit.json()["events"]
    unfinalize_events = [e for e in events if e["action"] == "UNFINALIZE"]
    assert unfinalize_events
    payload = unfinalize_events[-1]["payload"]
    assert payload.get("reason") == reason


def test_review_after_finalize_is_409(client: TestClient) -> None:
    process_id = _seed_completed(client)
    # SUSPICION ещё можно было бы CONFIRM по finding-машине — gate процесса должен закрыть.
    app.state.workspace.put_finding(
        process_id,
        Finding(
            finding_id="f-lock",
            evidence_group_id="eg-lock",
            rule_code="PZ-001",
            finding_status=FindingStatus.SUSPICION,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        ),
    )
    _finalize(client, process_id)
    review = client.post(
        "/api/v1/findings/f-lock/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "нельзя после FINALIZED",
        },
    )
    assert review.status_code == 409
    assert "финализ" in review.json()["detail"].lower()
