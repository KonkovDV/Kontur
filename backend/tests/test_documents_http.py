"""Список документов и PNG страницы."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_pdf_tokens import ascii_pdf

from kontur.application.runtime import AcceptedFile, ProcessWorkspace
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage, Finding
from kontur.domain.statuses import Completeness, FindingStatus, ReviewPriority
from kontur.infrastructure.pdfium_tokens import file_sha256
from kontur.presentation.api import app

INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


def _seed() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


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
