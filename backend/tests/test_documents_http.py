"""Список документов и PNG страницы."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from test_pdf_tokens import ascii_pdf

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage, Finding
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState, ReviewPriority
from kontur.infrastructure.pdfium_tokens import file_sha256
from kontur.presentation.api import app

INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}
SELECT_COMMENT = "В комплекте это последняя утверждённая редакция тома ПЗ."


def _seed() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _attach(
    workspace: ProcessWorkspace,
    record_id: str,
    *,
    file_id: str,
    stage: DocStage,
    payload: bytes,
    filename: str,
) -> None:
    record = workspace.get(record_id)
    assert record is not None
    item = AcceptedFile(
        file_id=file_id,
        file_hash=file_sha256(payload),
        filename=filename,
        doc_stage=stage,
        size_bytes=len(payload),
    )
    workspace.attach_file(record, item)
    workspace.keep_blob(record, file_id, payload)


def _by_file_id(body: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = body["documents"]
    assert isinstance(rows, list)
    mapping: dict[str, dict[str, object]] = {}
    for row in rows:
        assert isinstance(row, dict)
        mapping[str(row["file_id"])] = row
    return mapping


def test_documents_list_marks_single_pd_as_package_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    payload = ascii_pdf("PD sheet")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    record = app.state.workspace.create("obj-1", _seed())
    item = AcceptedFile(
        file_id="f-pd",
        file_hash=file_sha256(payload),
        filename="pd.pdf",
        doc_stage=DocStage.PD,
        size_bytes=len(payload),
    )
    app.state.workspace.attach_file(record, item)
    app.state.workspace.keep_blob(record, "f-pd", payload)

    listed = client.get(
        f"/api/v1/processes/{record.process_id}/documents",
        headers=INSPECTOR,
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["documents"][0]["approval_basis"] == "PACKAGE_DEFAULT"
    assert body["documents"][0]["actuality"] == "CURRENT"
    assert body["documents"][0]["doc_stage"] == "PD"

    page = client.get(
        f"/api/v1/processes/{record.process_id}/files/f-pd/pages/1.png",
        headers=INSPECTOR,
    )
    assert page.status_code == 200
    assert page.content.startswith(b"\x89PNG")

    cropped = client.get(
        f"/api/v1/processes/{record.process_id}/files/f-pd/pages/1.png",
        params={"bbox": "0.1,0.1,0.4,0.4"},
        headers=INSPECTOR,
    )
    assert cropped.status_code == 200
    assert cropped.content.startswith(b"\x89PNG")

    bad = client.get(
        f"/api/v1/processes/{record.process_id}/files/f-pd/pages/1.png",
        params={"bbox": "nope"},
        headers=INSPECTOR,
    )
    assert bad.status_code == 400

    missing = client.get(
        f"/api/v1/processes/{record.process_id}/files/f-pd/pages/9.png",
        headers=INSPECTOR,
    )
    assert missing.status_code == 404


def test_findings_list_returns_status_without_page_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    record = app.state.workspace.create("obj-1", _seed())
    app.state.workspace.put_finding(
        record.process_id,
        Finding(
            finding_id="f-low",
            rule_code="PZ-001",
            finding_status=FindingStatus.LOW_QUALITY,
            review_priority=ReviewPriority.LOW,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
            rationale="PD: якорь или число не найдены",
        ),
    )
    listed = client.get(
        f"/api/v1/processes/{record.process_id}/findings",
        headers=INSPECTOR,
    )
    assert listed.status_code == 200
    row = listed.json()["findings"][0]
    assert row["finding_status"] == "LOW_QUALITY"
    assert row["rule_code"] == "PZ-001"
    assert "страниц" not in listed.text


def _pd_rd() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def test_http_catalog_after_select_marks_same_cipher_superseded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Два ПД одного шифра без successor — не последний upload. Чужой шифр жив."""

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    early = ascii_pdf("CODE 12345-PZ Rev 1")
    late = ascii_pdf("CODE 12345-PZ Rev 2")
    other = ascii_pdf("CODE 22222-AR")
    rd = ascii_pdf("RD sheet")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    workspace = app.state.workspace
    record = workspace.create("obj-1", _pd_rd())
    _attach(
        workspace,
        record.process_id,
        file_id="f-early",
        stage=DocStage.PD,
        payload=early,
        filename="early.pdf",
    )
    _attach(
        workspace,
        record.process_id,
        file_id="f-late",
        stage=DocStage.PD,
        payload=late,
        filename="late.pdf",
    )
    _attach(
        workspace,
        record.process_id,
        file_id="f-ar",
        stage=DocStage.PD,
        payload=other,
        filename="ar.pdf",
    )
    _attach(
        workspace,
        record.process_id,
        file_id="f-rd",
        stage=DocStage.RD,
        payload=rd,
        filename="rd.pdf",
    )
    workspace.run_matrix_pipeline(record)

    listed = client.get(
        f"/api/v1/processes/{record.process_id}/documents",
        headers=INSPECTOR,
    )
    assert listed.status_code == 200
    before = _by_file_id(listed.json())
    assert before["f-early"]["actuality"] == "CLARIFICATION_REQUIRED"
    assert before["f-late"]["actuality"] == "CLARIFICATION_REQUIRED"
    assert before["f-ar"]["actuality"] == "CURRENT"
    assert before["f-ar"]["approval_basis"] == "PACKAGE_DEFAULT"
    assert before["f-rd"]["actuality"] == "CURRENT"

    findings = client.get(
        f"/api/v1/processes/{record.process_id}/findings",
        headers=INSPECTOR,
    )
    assert findings.status_code == 200
    pz = next(
        item
        for item in findings.json()["findings"]
        if item["rule_code"] == "PZ-001"
    )
    assert pz["finding_status"] == "CLARIFICATION_REQUIRED"
    assert "несколько редакций" in pz["rationale"]
    assert pz["finding_status"] != "CONFIRMED_VIOLATION"

    selected = client.post(
        f"/api/v1/processes/{record.process_id}/revisions/f-early/select",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7", "comment": SELECT_COMMENT},
    )
    assert selected.status_code == 200
    status = selected.json()
    assert status["process_state"] == "READY"
    assert status["counters"]["confirmed_violations"] == 0

    listed_after = client.get(
        f"/api/v1/processes/{record.process_id}/documents",
        headers=INSPECTOR,
    )
    assert listed_after.status_code == 200
    after = _by_file_id(listed_after.json())
    assert after["f-early"]["actuality"] == "CURRENT"
    assert after["f-early"]["approval_basis"] == "INSPECTOR_SELECT"
    assert after["f-late"]["actuality"] == "SUPERSEDED"
    assert after["f-ar"]["actuality"] == "CURRENT"
    assert after["f-ar"]["approval_basis"] == "PACKAGE_DEFAULT"
    assert after["f-rd"]["actuality"] == "CURRENT"

    findings_after = client.get(
        f"/api/v1/processes/{record.process_id}/findings",
        headers=INSPECTOR,
    )
    assert findings_after.status_code == 200
    rows = findings_after.json()["findings"]
    pz_after = next(item for item in rows if item["rule_code"] == "PZ-001")
    assert pz_after["finding_status"] != "CLARIFICATION_REQUIRED"
    assert pz_after["finding_status"] != "CONFIRMED_VIOLATION"
    assert "несколько редакций" not in (pz_after.get("rationale") or "")

    workspace.put_finding(
        record.process_id,
        Finding(
            finding_id="f-missing-stage",
            rule_code="IOS4-078",
            finding_status=FindingStatus.MISSING_EVIDENCE,
            review_priority=ReviewPriority.LOW,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
            rationale="ID не представлен, сравнение не запускалось",
        ),
    )
    blocked = client.post(
        "/api/v1/findings/f-missing-stage/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "нет стадии нельзя подтвердить как нарушение",
        },
    )
    assert blocked.status_code == 409
    still = client.get(
        f"/api/v1/processes/{record.process_id}/findings",
        headers=INSPECTOR,
    )
    stuck = next(
        item
        for item in still.json()["findings"]
        if item["finding_id"] == "f-missing-stage"
    )
    assert stuck["finding_status"] == "MISSING_EVIDENCE"


def _candidate(finding_id: str, rule_code: str) -> Finding:
    return Finding(
        finding_id=finding_id,
        evidence_group_id=f"eg-{finding_id}",
        rule_code=rule_code,
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        rationale="расхождение для очереди инспектора",
    )


def test_http_confirm_reject_then_download_protocol_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit Д2: подтвердил, отклонил с reason_code, протокол и журнал."""

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    record = app.state.workspace.create("obj-1", _seed())
    record.process_state = ProcessState.READY
    app.state.workspace.put_finding(record.process_id, _candidate("f-confirm", "PZ-001"))
    app.state.workspace.put_finding(record.process_id, _candidate("f-reject", "KR-055"))

    blocked = client.post(
        "/api/v1/findings/f-reject/review",
        headers=INSPECTOR,
        json={
            "action": "REJECT",
            "inspector_id": "insp-7",
            "comment": "отклонение без причины",
        },
    )
    assert blocked.status_code == 409

    too_early = client.post(
        f"/api/v1/processes/{record.process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert too_early.status_code == 409

    confirmed = client.post(
        "/api/v1/findings/f-confirm/review",
        headers=INSPECTOR,
        json={
            "action": "CONFIRM",
            "inspector_id": "insp-7",
            "comment": "площадь в РД меньше утверждённой ПД",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["finding_status"] == "CONFIRMED_VIOLATION"

    rejected = client.post(
        "/api/v1/findings/f-reject/review",
        headers=INSPECTOR,
        json={
            "action": "REJECT",
            "inspector_id": "insp-7",
            "reason_code": "APPROVED_CHANGE_EXISTS",
            "comment": "изменение утверждено отдельным листом",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["finding_status"] == "NEGATIVE_VERIFIED"

    completed = client.post(
        f"/api/v1/processes/{record.process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert completed.status_code == 200
    assert completed.json()["process_state"] == "COMPLETED"
    assert completed.json()["counters"]["confirmed_violations"] == 1
    assert completed.json()["counters"]["negative_verified"] == 1
    assert completed.json()["counters"]["candidates"] == 0

    finalized = client.post(
        f"/api/v1/processes/{record.process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert finalized.status_code == 200
    assert finalized.json()["process_state"] == "FINALIZED"

    protocol = client.get(
        f"/api/v1/processes/{record.process_id}/protocol",
        headers=INSPECTOR,
    )
    assert protocol.status_code == 200
    body = protocol.json()
    dumped = json.dumps(body)
    assert "AUTO_NO_DIFFERENCE" not in dumped
    assert body["violation_count"] == 1
    assert body["sections"]["confirmed"][0]["rule_code"] == "PZ-001"
    assert body["sections"]["negative_verified"][0]["rule_code"] == "KR-055"

    journal = client.get(
        f"/api/v1/processes/{record.process_id}/audit",
        headers=INSPECTOR,
    )
    assert journal.status_code == 200
    actions = [event["action"] for event in journal.json()["events"]]
    assert actions.count("REVIEW") == 2
    assert "COMPLETE_VERIFICATION" in actions
    assert "FINALIZE" in actions


def test_http_protocol_from_ready_without_candidates_goes_through_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без кандидатов очередь всё равно READY → VERIFYING → COMPLETED → FINALIZED."""

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    record = app.state.workspace.create("obj-1", _seed())
    record.process_state = ProcessState.READY
    app.state.workspace.put_finding(
        record.process_id,
        Finding(
            finding_id="f-missing",
            rule_code="AR-041",
            finding_status=FindingStatus.MISSING_EVIDENCE,
            review_priority=ReviewPriority.LOW,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
            rationale="ID не представлен, сравнение не запускалось",
        ),
    )
    skipped = client.post(
        f"/api/v1/processes/{record.process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert skipped.status_code == 409
    opened = client.post(
        f"/api/v1/processes/{record.process_id}/verify",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert opened.status_code == 200
    assert opened.json()["process_state"] == "VERIFYING"
    completed = client.post(
        f"/api/v1/processes/{record.process_id}/complete",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert completed.status_code == 200
    finalized = client.post(
        f"/api/v1/processes/{record.process_id}/finalize",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7"},
    )
    assert finalized.status_code == 200
    protocol = client.get(
        f"/api/v1/processes/{record.process_id}/protocol",
        headers=INSPECTOR,
    )
    assert protocol.status_code == 200
    assert protocol.json()["violation_count"] == 0
    assert "CONFIRMED_VIOLATION" not in json.dumps(protocol.json())


def test_http_select_refuses_explicit_not_approved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Кнопка эталона не перекрывает явный «не утв.»."""

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    payload = ascii_pdf("not approved CODE 12345-PZ")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    workspace = app.state.workspace
    record = workspace.create("obj-1", _seed())
    _attach(
        workspace,
        record.process_id,
        file_id="f-draft",
        stage=DocStage.PD,
        payload=payload,
        filename="draft.pdf",
    )
    workspace.run_matrix_pipeline(record)

    listed = client.get(
        f"/api/v1/processes/{record.process_id}/documents",
        headers=INSPECTOR,
    )
    assert listed.status_code == 200
    row = _by_file_id(listed.json())["f-draft"]
    assert row["approval_status"] == "NOT_APPROVED"
    assert row["approval_basis"] != "INSPECTOR_SELECT"

    refused = client.post(
        f"/api/v1/processes/{record.process_id}/revisions/f-draft/select",
        headers=INSPECTOR,
        json={"inspector_id": "insp-7", "comment": SELECT_COMMENT},
    )
    assert refused.status_code == 409
    assert "нельзя перекрыть" in refused.json()["detail"]

    again = client.get(
        f"/api/v1/processes/{record.process_id}/documents",
        headers=INSPECTOR,
    )
    kept = _by_file_id(again.json())["f-draft"]
    assert kept["approval_status"] == "NOT_APPROVED"
    assert kept["approval_basis"] != "INSPECTOR_SELECT"
    stored = app.state.workspace.get(record.process_id)
    assert stored is not None
    assert "f-draft" not in stored.inspector_approved_file_ids
