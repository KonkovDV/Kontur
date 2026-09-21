"""HTTP-контур: роли, object scope, intake и юридические переходы."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus, ProcessState, ReviewPriority
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"

INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}
OTHER_INSPECTOR = {"Authorization": "Bearer insp-8@obj-2/INSPECTOR"}
ADMIN = {"Authorization": "Bearer admin-1@obj-1/ADMIN"}
SUPERVISOR = {"Authorization": "Bearer sup-1@obj-1/SUPERVISOR"}
OTHER_SUPERVISOR = {"Authorization": "Bearer sup-2@obj-2/SUPERVISOR"}


@pytest.fixture
def client() -> TestClient:
    app.state.workspace = ProcessWorkspace()
    return TestClient(app)


def _upload(
    client: TestClient,
    *,
    name: str = "pz.pdf",
    headers: dict[str, str] = INSPECTOR,
    object_id: str = "obj-1",
):
    return client.post(
        "/api/v1/documents/upload",
        headers=headers,
        data={"object_id": object_id, "doc_stage": "PD"},
        files=[("files", (name, PDF, "application/pdf"))],
    )


def test_healthz_is_public(client: TestClient) -> None:
    assert client.get("/api/v1/healthz").json() == {"status": "ok"}


def test_capabilities_require_token(client: TestClient) -> None:
    assert client.get("/api/v1/system/capabilities").status_code == 401


def test_capabilities_allow_unscoped_role_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/system/capabilities",
        headers={"Authorization": "Bearer ADMIN"},
    )
    assert response.status_code == 200


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
    assert _upload(client, headers={}).status_code == 401


def test_upload_requires_matching_object_scope(client: TestClient) -> None:
    response = _upload(client, headers=OTHER_INSPECTOR)
    assert response.status_code == 403
    assert app.state.workspace._items == {}


def test_admin_cannot_upload_or_confirm(client: TestClient) -> None:
    assert _upload(client, headers=ADMIN).status_code == 403
    seeded = _seed_completed(client)
    response = client.post(
        f"/api/v1/processes/{seeded}/finalize",
        headers=ADMIN,
        json={"inspector_id": "admin-1"},
    )
    assert response.status_code == 403


def test_upload_accepts_pdf_and_reaches_ready(client: TestClient) -> None:
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
    assert payload["process_state"] == "READY"
    assert payload["completeness"]["pd"] == "PD_UPLOADED"
    assert payload["completeness"]["rd"] == "RD_MISSING"
    assert payload["counters"]["confirmed_violations"] == 0
    record = app.state.workspace.get(body["process_id"])
    assert record is not None
    assert len(record.findings) == 132
    assert all(
        item.finding_status is not FindingStatus.CONFIRMED_VIOLATION
        for item in record.findings.values()
    )


def test_cross_object_reads_are_denied(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    for suffix in ("status", "protocol", "audit"):
        response = client.get(
            f"/api/v1/processes/{process_id}/{suffix}",
            headers=OTHER_INSPECTOR,
        )
        assert response.status_code == 403, suffix


def test_unscoped_token_cannot_access_process(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    response = client.get(
        f"/api/v1/processes/{process_id}/status",
        headers={"Authorization": "Bearer ADMIN"},
    )
    assert response.status_code == 403


def test_cross_object_upload_has_no_side_effect(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    files_before = list(record.files)
    state_before = record.process_state
    response = client.post(
        "/api/v1/documents/upload",
        headers=OTHER_INSPECTOR,
        data={"object_id": "obj-2", "doc_stage": "RD", "process_id": process_id},
        files=[("files", ("rd.pdf", PDF + b"x", "application/pdf"))],
    )
    assert response.status_code == 403
    assert record.files == files_before
    assert record.process_state is state_before


def test_cross_object_review_has_no_side_effect(client: TestClient) -> None:
    process_id = _seed_completed(client, with_candidate=True)
    record = app.state.workspace.get(process_id)
    assert record is not None
    before = record.findings["eg-1"]
    audit_before = list(record.audit.records)
    response = client.post(
        "/api/v1/findings/f-1/review",
        headers=OTHER_INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-8",
            "comment": "атака через чужой finding_id",
        },
    )
    assert response.status_code == 403
    assert record.findings["eg-1"] == before
    assert record.audit.records == audit_before


def test_cross_object_state_transitions_have_no_side_effect(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    for path, headers, body in (
        ("verify", OTHER_INSPECTOR, {"inspector_id": "insp-8"}),
        ("complete", OTHER_INSPECTOR, {"inspector_id": "insp-8"}),
        ("finalize", OTHER_INSPECTOR, {"inspector_id": "insp-8"}),
        (
            "unfinalize",
            OTHER_SUPERVISOR,
            {"inspector_id": "sup-2", "reason": "атака"},
        ),
    ):
        before = record.process_state
        response = client.post(
            f"/api/v1/processes/{process_id}/{path}",
            headers=headers,
            json=body,
        )
        assert response.status_code == 403, path
        assert record.process_state is before
    sync = client.post(f"/api/v1/inspection/{process_id}", headers=OTHER_SUPERVISOR)
    assert sync.status_code == 403
    file_id = record.files[0].file_id
    select = client.post(
        f"/api/v1/processes/{process_id}/revisions/{file_id}/select",
        headers=OTHER_INSPECTOR,
        json={"inspector_id": "insp-8", "comment": "атака чужим object_id"},
    )
    assert select.status_code == 403


def test_inspector_selects_revision_and_does_not_write_violation(
    client: TestClient,
) -> None:
    uploaded = _upload(client)
    body = uploaded.json()
    process_id = body["process_id"]
    file_id = body["accepted"][0]["file_id"]
    response = client.post(
        f"/api/v1/processes/{process_id}/revisions/{file_id}/select",
        headers=INSPECTOR,
        json={
            "inspector_id": "insp-7",
            "comment": "Том ПД из комплекта организатора — эталон сравнения.",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["process_state"] == "READY"
    assert payload["counters"]["confirmed_violations"] == 0
    record = app.state.workspace.get(process_id)
    assert record is not None
    assert file_id in record.inspector_approved_file_ids
    assert any(action == "SELECT_REVISION" for _actor, action, _p in record.audit.records)
    admin = client.post(
        f"/api/v1/processes/{process_id}/revisions/{file_id}/select",
        headers=ADMIN,
        json={"inspector_id": "admin-1", "comment": "админ не выбирает эталон"},
    )
    assert admin.status_code == 403
    missing = client.post(
        f"/api/v1/processes/{process_id}/revisions/no-such-file/select",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7", "comment": "нет файла"},
    )
    assert missing.status_code == 404


def test_protocol_after_upload_is_draft_without_violations(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    response = client.get(f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY"
    assert body["violation_count"] == 0
    assert "AUTO_NO_DIFFERENCE" not in json.dumps(body)
    assert "preliminary_no_difference" not in body["sections"]


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


def test_protocol_lists_candidate_and_not_as_violation(client: TestClient) -> None:
    process_id = _seed_completed(client, with_candidate=True)
    body = client.get(
        f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR
    ).json()
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


def test_protocol_requires_token(client: TestClient) -> None:
    process_id = _seed_completed(client)
    assert client.get(f"/api/v1/processes/{process_id}/protocol").status_code == 401


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


def test_supervisor_can_unfinalize(client: TestClient) -> None:
    process_id = _seed_completed(client)
    client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
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


def test_duplicate_upload_same_hash_stage_is_empty_accepted(client: TestClient) -> None:
    first = _upload(client)
    process_id = first.json()["process_id"]
    retry = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD", "process_id": process_id},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert retry.status_code == 202
    assert retry.json()["accepted"] == []
    record = app.state.workspace.get(process_id)
    assert record is not None
    assert record.process_state is ProcessState.READY
    assert record.parse_attempts == 1
    assert len(record.findings) == 132


def test_audit_log_requires_token(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    assert client.get(f"/api/v1/processes/{process_id}/audit").status_code == 401


def test_audit_log_lists_review_events(client: TestClient) -> None:
    process_id = _seed_completed(client, with_candidate=True)
    client.post(
        "/api/v1/findings/f-1/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "совпало по штампу",
        },
    )
    response = client.get(f"/api/v1/processes/{process_id}/audit", headers=INSPECTOR)
    assert response.status_code == 200
    actions = [event["action"] for event in response.json()["events"]]
    assert "REVIEW" in actions


def test_audit_log_unknown_process_is_404(client: TestClient) -> None:
    response = client.get("/api/v1/processes/does-not-exist/audit", headers=INSPECTOR)
    assert response.status_code == 404


def test_finalize_from_ready_is_409(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    response = client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert response.status_code == 409


def test_admin_cannot_open_or_close_queue(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    assert client.post(
        f"/api/v1/processes/{process_id}/verify",
        headers=ADMIN,
        json={"inspector_id": "admin-1"},
    ).status_code == 403
    opened = client.post(
        f"/api/v1/processes/{process_id}/verify",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert opened.status_code == 200
    assert client.post(
        f"/api/v1/processes/{process_id}/complete",
        headers=ADMIN,
        json={"inspector_id": "admin-1"},
    ).status_code == 403


def test_ready_verify_complete_then_finalize(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    started = client.post(
        f"/api/v1/processes/{process_id}/verify",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert started.status_code == 200
    assert started.json()["process_state"] == "VERIFYING"
    _close_blocking(process_id)
    completed = client.post(
        f"/api/v1/processes/{process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert completed.status_code == 200
    finalized = client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert finalized.status_code == 200
    assert finalized.json()["process_state"] == "FINALIZED"
    body = client.get(
        f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR
    ).json()
    assert body["protocol_id"].startswith("protocol-")
    assert not body["protocol_id"].startswith("placeholder-")
    assert body["status"] == "PROTOCOL_FINALIZED"
    assert body["version"] == 1
    assert "preliminary_no_difference" not in body["sections"]
    undone = client.post(
        f"/api/v1/processes/{process_id}/unfinalize",
        headers=SUPERVISOR,
        json={"inspector_id": "sup-1", "reason": "ошибочная финализация"},
    )
    assert undone.status_code == 200
    again = client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert again.status_code == 200
    v2 = client.get(
        f"/api/v1/processes/{process_id}/protocol", headers=INSPECTOR
    ).json()
    assert v2["version"] == 2
    assert v2["protocol_id"].endswith("-v2")
    historic = client.get(
        f"/api/v1/processes/{process_id}/protocol",
        headers=INSPECTOR,
        params={"version": 1},
    )
    assert historic.status_code == 200
    assert historic.json()["version"] == 1
    assert historic.json()["protocol_id"] == body["protocol_id"]


def test_candidate_blocks_complete_and_finalize(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    assert client.post(
        f"/api/v1/processes/{process_id}/verify",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    ).status_code == 200
    _close_blocking(process_id)
    app.state.workspace.put_finding(
        process_id,
        Finding(
            finding_id="f-open",
            evidence_group_id="eg-open",
            rule_code="PZ-001",
            finding_status=FindingStatus.CANDIDATE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        ),
    )
    assert client.post(
        f"/api/v1/processes/{process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    ).status_code == 409
    assert client.post(
        f"/api/v1/processes/{process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    ).status_code == 409
    reviewed = client.post(
        "/api/v1/findings/f-open/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "совпало по штампу",
        },
    )
    assert reviewed.status_code == 200
    closed = client.post(
        f"/api/v1/processes/{process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert closed.status_code == 200


def test_first_review_opens_verification_queue(client: TestClient) -> None:
    process_id = _upload(client).json()["process_id"]
    _close_blocking(process_id)
    app.state.workspace.put_finding(
        process_id,
        Finding(
            finding_id="f-first",
            evidence_group_id="eg-first",
            rule_code="PZ-001",
            finding_status=FindingStatus.CANDIDATE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        ),
    )
    reviewed = client.post(
        "/api/v1/findings/f-first/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "совпало по штампу",
        },
    )
    assert reviewed.status_code == 200
    status = client.get(f"/api/v1/processes/{process_id}/status", headers=INSPECTOR)
    assert status.json()["process_state"] == "VERIFYING"


def _close_blocking(process_id: str) -> None:
    record = app.state.workspace.get(process_id)
    assert record is not None
    blocking = {FindingStatus.CANDIDATE, FindingStatus.SUSPICION}
    for key, finding in list(record.findings.items()):
        if finding.finding_status in blocking:
            record.findings[key] = replace(
                finding, finding_status=FindingStatus.MISSING_EVIDENCE
            )


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
