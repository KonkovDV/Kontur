"""HTTP-контур: приём, роли и повторы вызываются из FastAPI, а не только из pytest."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus, ProcessState, ReviewPriority
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"

INSPECTOR = {"Authorization": "Bearer insp-7/INSPECTOR"}
ADMIN = {"Authorization": "Bearer admin-1/ADMIN"}
SUPERVISOR = {"Authorization": "Bearer sup-1/SUPERVISOR"}


@pytest.fixture
def client() -> TestClient:
    app.state.workspace = ProcessWorkspace()
    return TestClient(app)


def _upload(client: TestClient, *, name: str = "pz.pdf", headers: dict[str, str] = INSPECTOR):
    return client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", (name, PDF, "application/pdf"))],
    )


def test_healthz_is_public(client: TestClient) -> None:
    assert client.get("/api/v1/healthz").json() == {"status": "ok"}


def test_capabilities_require_token(client: TestClient) -> None:
    assert client.get("/api/v1/system/capabilities").status_code == 401


def test_capabilities_are_honest_about_missing_ocr(client: TestClient) -> None:
    response = client.get("/api/v1/system/capabilities", headers=INSPECTOR)
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] == "AVAILABLE"
    assert body["kit_blocked"] is False
    engines = {item["name"]: item for item in body["engines"]}
    assert engines["vector_text"]["status"] == "AVAILABLE"
    assert engines["ocr_text"]["status"] == "UNAVAILABLE"
    assert engines["drawing_analysis"]["status"] == "UNAVAILABLE"
    assert "ocr_text" in body["health"]["failed"]
    assert "vector_text" in body["health"]["healthy"]
    assert "overall_kit_status" not in body
    assert "engine_status" not in body


def test_upload_without_token_is_401(client: TestClient) -> None:
    response = _upload(client, headers={})
    assert response.status_code == 401


def test_admin_cannot_upload_or_confirm(client: TestClient) -> None:
    assert _upload(client, headers=ADMIN).status_code == 403
    seeded = _seed_completed(client)
    response = client.post(
        f"/api/v1/processes/{seeded}/finalize",
        headers=ADMIN,
        json={"inspector_id": "admin-1"},
    )
    assert response.status_code == 403


def test_upload_accepts_pdf_and_stays_in_parsing(client: TestClient) -> None:
    response = _upload(client)
    assert response.status_code == 202
    body = response.json()
    assert body["rejected"] == []
    assert body["accepted"][0]["file_hash"] == hashlib.sha256(PDF).hexdigest()
    status = client.get(
        f"/api/v1/processes/{body['process_id']}/status", headers=INSPECTOR
    )
    assert status.status_code == 200
    payload = status.json()
    assert payload["process_state"] == "PARSING"
    assert payload["completeness"]["pd"] == "PD_UPLOADED"
    assert payload["completeness"]["rd"] == "RD_MISSING"


def test_zip_named_as_pdf_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", ("fake.pdf", b"PK\x03\x04data", "application/pdf"))],
    )
    assert response.status_code == 422
    assert response.json()["reason_code"] == "CORRUPTED_FILE"


def test_unsafe_filename_never_creates_a_process(client: TestClient) -> None:
    response = _upload(client, name="../../etc/passwd.pdf")
    assert response.status_code == 422
    assert response.json()["reason_code"] == "UNSAFE_FILENAME"


def test_content_length_limit_is_enforced_before_intake(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kontur.presentation.api.MAX_BATCH_BYTES", 10)
    response = _upload(client)
    assert response.status_code == 413
    assert response.json()["reason_code"] == "BATCH_LIMIT_EXCEEDED"


def test_protocol_is_not_invented(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    response = client.get(f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR)
    assert response.status_code == 404
    assert "не собран" in response.json()["detail"]


def test_protocol_available_after_completed(client: TestClient) -> None:
    process_id = _seed_completed(client)
    response = client.get(f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR)
    assert response.status_code == 200
    body = response.json()
    assert body["object_id"] == "obj-1"
    assert body["status"] == "VERIFICATION_COMPLETED"
    assert "process_state" not in body
    assert isinstance(body["sections"]["candidates"], list)
    assert body["violation_count"] == 0
    assert "preliminary_no_difference" not in body["sections"]


def test_protocol_lists_candidate_and_not_as_violation(client: TestClient) -> None:
    process_id = _seed_completed(client, with_candidate=True)
    response = client.get(f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR)
    assert response.status_code == 200
    body = response.json()
    candidates = body["sections"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["rule_code"] == "PZ-001"
    assert candidates[0]["finding_status"] == "CANDIDATE"
    assert body["violation_count"] == 0


def test_protocol_keeps_auto_no_difference_off_the_tz_wire(client: TestClient) -> None:
    process_id = _seed_completed(client, with_candidate=True)
    app.state.workspace.put_finding(
        process_id,
        Finding(
            finding_id="f-eq",
            evidence_group_id="eg-eq",
            rule_code="PZ-001",
            finding_status=FindingStatus.AUTO_NO_DIFFERENCE,
            review_priority=ReviewPriority.LOW,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        ),
    )
    body = client.get(
        f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR
    ).json()
    assert "AUTO_NO_DIFFERENCE" not in json.dumps(body)
    assert body["sections"]["candidates"][0]["finding_status"] == "CANDIDATE"


def test_protocol_404_for_unknown_process(client: TestClient) -> None:
    response = client.get("/api/v1/processes/does-not-exist/protocol", headers=INSPECTOR)
    assert response.status_code == 404
    assert "не найден" in response.json()["detail"]


def test_protocol_requires_token(client: TestClient) -> None:
    process_id = _seed_completed(client)
    response = client.get(f"/api/v1/processes/{process_id}/protocol")
    assert response.status_code == 401


def test_review_and_finalize_require_matching_subject(client: TestClient) -> None:
    process_id = _seed_completed(client, with_candidate=True)
    forbidden = client.post(
        "/api/v1/findings/f-1/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "someone-else",
            "comment": "совпало по штампу",
        },
    )
    assert forbidden.status_code == 403
    ok = client.post(
        "/api/v1/findings/f-1/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "совпало по штампу",
        },
    )
    assert ok.status_code == 200
    assert ok.json()["finding_status"] == "CONFIRMED_VIOLATION"
    finalized = client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert finalized.status_code == 200
    assert finalized.json()["process_state"] == "FINALIZED"


def test_sync_before_finalize_is_409_and_retries_are_finite(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    early = client.post(f"/api/v1/inspection/{process_id}", headers=SUPERVISOR)
    assert early.status_code == 409
    completed = _seed_completed(client)
    client.post(
        f"/api/v1/processes/{completed}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    first = client.post(f"/api/v1/inspection/{completed}", headers=SUPERVISOR)
    assert first.status_code == 202
    assert first.json() == "PENDING_SYNC"
    second = client.post(f"/api/v1/inspection/{completed}", headers=SUPERVISOR)
    assert second.status_code == 202
    assert second.json() == "RETRY_WAIT"


def test_role_only_bearer_is_enough_for_status(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    response = client.get(
        f"/api/v1/processes/{process_id}/status",
        headers={"Authorization": "Bearer ADMIN"},
    )
    assert response.status_code == 200


def test_supervisor_can_unfinalize(client: TestClient) -> None:
    process_id = _seed_completed(client)
    assert (
        client.post(
            f"/api/v1/processes/{process_id}/finalize",
            headers=INSPECTOR,
            json={"inspector_id": "insp-7"},
        ).status_code
        == 200
    )
    response = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=SUPERVISOR,
        json={"inspector_id": "sup-1", "reason": "ошибка редакции"},
    )
    assert response.status_code == 200
    assert response.json()["process_state"] == "COMPLETED"


def test_inspector_cannot_unfinalize(client: TestClient) -> None:
    process_id = _seed_completed(client)
    client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    response = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7", "reason": "ошибка редакции"},
    )
    assert response.status_code == 403


def _seed_completed(client: TestClient, *, with_candidate: bool = False) -> str:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    record.process_state = ProcessState.COMPLETED
    if with_candidate:
        app.state.workspace.put_finding(
            process_id,
            Finding(
                finding_id="f-1",
                evidence_group_id="eg-1",
                rule_code="PZ-001",
                finding_status=FindingStatus.CANDIDATE,
                review_priority=ReviewPriority.HIGH,
                matrix_version="draft-0",
                rule_version="0.1.0",
                model_version="none",
            ),
        )
    return process_id
