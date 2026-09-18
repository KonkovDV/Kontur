"""GET /api/v1/processes/{id}/audit \u2014 \u0436\u0443\u0440\u043d\u0430\u043b \u043f\u0440\u0430\u0432\u043e\u043a (Gate K / GAP-EDIT \u0447\u0430\u0441\u0442\u0438\u0447\u043d\u043e).\n
\u041f\u043e\u043a\u0440\u044b\u0432\u0430\u0435\u0442:\n- \u043f\u0443\u0441\u0442\u043e\u0439 \u0436\u0443\u0440\u043d\u0430\u043b \u0441\u0440\u0430\u0437\u0443 \u043f\u043e\u0441\u043b\u0435 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438\n- REVIEW-\u0441\u043e\u0431\u044b\u0442\u0438\u0435 \u043f\u043e\u0441\u043b\u0435 reviewFinding \u0441 finding_id \u0432 payload\n- 404 \u0434\u043b\u044f \u043d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e\u0433\u043e \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0430\n- 401 \u0431\u0435\u0437 \u0442\u043e\u043a\u0435\u043d\u0430\n- \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0432\u0441\u0435\u043c \u0442\u0440\u0451\u043c \u0440\u043e\u043b\u044f\u043c\n"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus, ProcessState, ReviewPriority
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7/INSPECTOR"}
SUPERVISOR = {"Authorization": "Bearer sup-1/SUPERVISOR"}
ADMIN = {"Authorization": "Bearer admin-1/ADMIN"}


@pytest.fixture
def client() -> TestClient:
    app.state.workspace = ProcessWorkspace()
    return TestClient(app)


def _upload(client: TestClient) -> str:
    res = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-audit", "doc_stage": "PD"},
        files=[("files", ("probe.pdf", PDF, "application/pdf"))],
    )
    assert res.status_code == 202
    return res.json()["process_id"]


def _seed_with_candidate(client: TestClient) -> str:
    """\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 + COMPLETED + \u043a\u0430\u043d\u0434\u0438\u0434\u0430\u0442 f-1 (\u043a\u0430\u043a \u0432 test_api.py::_seed_completed)."""
    pid = _upload(client)
    record = app.state.workspace.get(pid)
    assert record is not None
    record.process_state = ProcessState.COMPLETED
    app.state.workspace.put_finding(
        pid,
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
    return pid


def test_audit_empty_right_after_upload(client: TestClient) -> None:
    pid = _upload(client)
    res = client.get(f"/api/v1/processes/{pid}/audit", headers=INSPECTOR)
    assert res.status_code == 200
    body = res.json()
    assert body["process_id"] == pid
    assert body["total"] == 0
    assert body["events"] == []


def test_audit_captures_review_event(client: TestClient) -> None:
    pid = _seed_with_candidate(client)

    review_res = client.post(
        "/api/v1/findings/f-1/review",
        headers=INSPECTOR,
        json={"action": "CONFIRM", "inspector_id": "insp-7", "comment": "\u043f\u043e \u0448\u0442\u0430\u043c\u043f\u0443"},
    )
    assert review_res.status_code == 200

    res = client.get(f"/api/v1/processes/{pid}/audit", headers=INSPECTOR)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    event = body["events"][0]
    assert event["seq"] == 0
    assert event["actor_id"] == "insp-7"
    assert event["action"] == "REVIEW"
    assert event["payload"]["finding_id"] == "f-1"


def test_audit_review_payload_contains_action(client: TestClient) -> None:
    pid = _seed_with_candidate(client)
    client.post(
        "/api/v1/findings/f-1/review",
        headers=INSPECTOR,
        json={"action": "CONFIRM", "inspector_id": "insp-7", "comment": "\u043e\u043a"},
    )
    events = client.get(f"/api/v1/processes/{pid}/audit", headers=INSPECTOR).json()["events"]
    assert events[0]["payload"]["action"] == "CONFIRM"


def test_audit_404_for_unknown_process(client: TestClient) -> None:
    res = client.get("/api/v1/processes/nonexistent/audit", headers=INSPECTOR)
    assert res.status_code == 404
    assert "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d" in res.json()["detail"]


def test_audit_401_without_token(client: TestClient) -> None:
    pid = _upload(client)
    res = client.get(f"/api/v1/processes/{pid}/audit")
    assert res.status_code == 401


def test_audit_accessible_to_supervisor_and_admin(client: TestClient) -> None:
    pid = _upload(client)
    assert client.get(f"/api/v1/processes/{pid}/audit", headers=SUPERVISOR).status_code == 200
    assert client.get(f"/api/v1/processes/{pid}/audit", headers=ADMIN).status_code == 200
