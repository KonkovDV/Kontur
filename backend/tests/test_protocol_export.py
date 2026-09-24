"""DOCX и XML протокола из того же провода, что JSON. PDF честно отсутствует."""

from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient

from kontur.application.protocol_export import ProtocolPdfUnavailable, render_pdf
from kontur.application.runtime import ProcessWorkspace
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7@obj-1/INSPECTOR"}


def test_docx_and_xml_follow_the_json_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-1", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert uploaded.status_code == 202
    process_id = uploaded.json()["process_id"]
    docx = client.get(f"/api/v1/processes/{process_id}/protocol.docx", headers=INSPECTOR)
    xml = client.get(f"/api/v1/processes/{process_id}/protocol.xml", headers=INSPECTOR)
    pdf = client.get(f"/api/v1/processes/{process_id}/protocol.pdf", headers=INSPECTOR)
    assert docx.status_code == 200
    assert docx.content.startswith(b"PK")
    assert b"AUTO_NO_DIFFERENCE" not in docx.content
    document = Document(BytesIO(docx.content))
    headings = [paragraph.text for paragraph in document.paragraphs]
    for title in (
        "Статус загрузки документов",
        "Тип проверки",
        "Комплектность",
        "Кандидаты",
        "Подтверждённые нарушения",
        "Нарушение не подтверждено",
        "Подозрения",
        "Карточки доказательств",
    ):
        assert title in headings
    assert len(document.tables) == 6
    assert xml.status_code == 200
    text = xml.content.decode("utf-8")
    assert "check_type" in text
    assert "upload_status" in text
    assert "evidence_cards" in text
    assert "AUTO_NO_DIFFERENCE" not in text
    assert pdf.status_code == 501
    body = pdf.json()
    assert "GAP-PROTOCOL-PDF" in body["detail"]
    assert "gap" not in body
    with pytest.raises(ProtocolPdfUnavailable, match="GAP-PROTOCOL-PDF"):
        render_pdf({})
