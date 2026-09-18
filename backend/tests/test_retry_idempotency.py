"""Gate L: retry не даёт дублей (п. 9.1, п. 9.6).

Покрывает:
- attach_file: повторный хеш (совпадающий file_hash + doc_stage) не дублируется
- attach_file: одинаковый хеш, но разная стадия — не дубликат (PD и RD разные)
- put_finding: повтор evidence_group_id перезаписывает, не дублирует
- upload API: повторный POST /upload с тем же файлом не удваивает количество accepted
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.domain.models import DocStage, Finding
from kontur.domain.statuses import (
    Completeness,
    FindingStatus,
    ProcessState,
    ReviewPriority,
    Scenario,
)
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
INSPECTOR = {"Authorization": "Bearer insp-7/INSPECTOR"}


@pytest.fixture
def client() -> TestClient:
    app.state.workspace = ProcessWorkspace()
    return TestClient(app)


def _make_record() -> tuple[ProcessWorkspace, ProcessRecord]:
    ws = ProcessWorkspace()
    completeness = {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    record = ws.create("obj-idem", completeness)
    return ws, record


def _make_file(hash_val: str, stage: DocStage = DocStage.PD) -> AcceptedFile:
    return AcceptedFile(
        file_id="fid-" + hash_val[:8],
        file_hash=hash_val,
        filename="probe.pdf",
        doc_stage=stage,
        size_bytes=100,
    )


# ---------------------------------------------------------------------------
# attach_file idempotency
# ---------------------------------------------------------------------------


class TestAttachFileIdempotency:
    def test_first_attach_returns_true(self) -> None:
        ws, record = _make_record()
        f = _make_file("aabbcc")
        assert ws.attach_file(record, f) is True

    def test_duplicate_hash_and_stage_returns_false(self) -> None:
        ws, record = _make_record()
        f = _make_file("aabbcc")
        ws.attach_file(record, f)
        result = ws.attach_file(record, _make_file("aabbcc"))  # same hash+stage
        assert result is False

    def test_duplicate_does_not_grow_files_list(self) -> None:
        ws, record = _make_record()
        ws.attach_file(record, _make_file("aabbcc"))
        ws.attach_file(record, _make_file("aabbcc"))
        assert len(record.files) == 1

    def test_same_hash_different_stage_is_new_attachment(self) -> None:
        """Одинаковый хеш, но разные стадии (напр., PD и RD) — разные файлы."""
        ws, record = _make_record()
        result1 = ws.attach_file(record, _make_file("aabbcc", DocStage.PD))
        result2 = ws.attach_file(record, _make_file("aabbcc", DocStage.RD))
        assert result1 is True
        assert result2 is True
        assert len(record.files) == 2

    def test_different_hash_same_stage_is_new_attachment(self) -> None:
        ws, record = _make_record()
        ws.attach_file(record, _make_file("hash-v1"))
        result = ws.attach_file(record, _make_file("hash-v2"))  # новая версия файла
        assert result is True
        assert len(record.files) == 2


# ---------------------------------------------------------------------------
# put_finding idempotency (already tested in RT-G, but verified here too)
# ---------------------------------------------------------------------------


class TestPutFindingIdempotency:
    def test_same_evidence_group_overwrites_not_duplicates(self) -> None:
        ws, record = _make_record()
        f1 = Finding(
            finding_id="f-1",
            evidence_group_id="eg-1",
            rule_code="PZ-001",
            finding_status=FindingStatus.CANDIDATE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        )
        f2 = Finding(
            finding_id="f-1b",
            evidence_group_id="eg-1",  # тот же evidence_group_id
            rule_code="PZ-001",
            finding_status=FindingStatus.CANDIDATE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        )
        ws.put_finding(record.process_id, f1)
        ws.put_finding(record.process_id, f2)
        assert len(record.findings) == 1  # не два, а одна
        assert record.findings["eg-1"].finding_id == "f-1b"  # перезаписались

    def test_different_evidence_groups_coexist(self) -> None:
        ws, record = _make_record()
        for i in range(3):
            ws.put_finding(
                record.process_id,
                Finding(
                    finding_id=f"f-{i}",
                    evidence_group_id=f"eg-{i}",
                    rule_code="PZ-001",
                    finding_status=FindingStatus.CANDIDATE,
                    review_priority=ReviewPriority.HIGH,
                    matrix_version="draft-0",
                    rule_version="0.1.0",
                    model_version="none",
                ),
            )
        assert len(record.findings) == 3


# ---------------------------------------------------------------------------
# Upload API: HTTP retry не даёт дублей в accepted
# ---------------------------------------------------------------------------


def test_http_upload_retry_same_file_no_duplicate(client: TestClient) -> None:
    """Два POST с одинаковым контентом: оба 202, но процесс один; второй
    возвращает пустой accepted[] (файл уже есть).
    """
    res1 = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-retry", "doc_stage": "PD"},
        files=[("files", ("doc.pdf", PDF, "application/pdf"))],
    )
    assert res1.status_code == 202
    pid = res1.json()["process_id"]
    assert len(res1.json()["accepted"]) == 1

    # точный retry: тот же object_id + process_id + тот же файл
    res2 = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-retry", "doc_stage": "PD", "process_id": pid},
        files=[("files", ("doc.pdf", PDF, "application/pdf"))],
    )
    assert res2.status_code == 202
    assert res2.json()["process_id"] == pid
    # файл уже есть — accepted пустой
    assert res2.json()["accepted"] == []


def test_http_upload_different_file_same_stage_accepted(client: TestClient) -> None:
    """Новый файл (иной хеш) на ту же стадию — принимается."""
    res1 = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-new", "doc_stage": "PD"},
        files=[("files", ("v1.pdf", PDF, "application/pdf"))],
    )
    pid = res1.json()["process_id"]

    res2 = client.post(
        "/api/v1/documents/upload",
        headers=INSPECTOR,
        data={"object_id": "obj-new", "doc_stage": "PD", "process_id": pid},
        files=[("files", ("v2.pdf", PDF + b"extra", "application/pdf"))],
    )
    assert res2.status_code == 202
    assert len(res2.json()["accepted"]) == 1  # новый файл принят
