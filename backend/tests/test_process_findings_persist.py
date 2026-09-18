"""GAP-PROCESS-FINDINGS: findings survive a workspace restart (same MemoryProcessStore).

Покрывает:
- факт выживания после рестарта
- идемпотентность AT-LEAST-ONCE по evidence_group_id
- находка без группы (ключ = finding_id)
- независимость процессов: находки не перемешиваются
"""

from __future__ import annotations

import pytest

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import DocStage, Finding
from kontur.domain.statuses import Completeness, FindingStatus, ReviewPriority
from kontur.infrastructure.db.process_store import MemoryProcessStore


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def _finding(
    finding_id: str = "f-1",
    rule_code: str = "PZ-001",
    evidence_group_id: str | None = "eg-1",
    status: FindingStatus = FindingStatus.CANDIDATE,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        rule_code=rule_code,
        finding_status=status,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=evidence_group_id,
    )


def test_findings_survive_workspace_restart() -> None:
    """ProcessWorkspace →1 покладывает находку, ProcessWorkspace#2 её зачитывает."""
    store = MemoryProcessStore()

    ws1 = ProcessWorkspace(store)
    record = ws1.create("obj-1", _completeness())
    pid = record.process_id
    ws1.put_finding(pid, _finding())

    # Simulate restart: same store, brand-new workspace instance.
    ws2 = ProcessWorkspace(store)
    restored = ws2.get(pid)
    assert restored is not None
    assert "eg-1" in restored.findings
    assert restored.findings["eg-1"].rule_code == "PZ-001"
    assert restored.findings["eg-1"].finding_status is FindingStatus.CANDIDATE


def test_put_finding_is_idempotent_by_evidence_group_id() -> None:
    """Повторный put_finding с тем же evidence_group_id перезаписывает, не дублирует."""
    store = MemoryProcessStore()
    ws1 = ProcessWorkspace(store)
    record = ws1.create("obj-2", _completeness())
    pid = record.process_id

    f1 = _finding(finding_id="f-1", status=FindingStatus.CANDIDATE)
    f2 = _finding(finding_id="f-2", status=FindingStatus.CONFIRMED_VIOLATION)
    ws1.put_finding(pid, f1)
    ws1.put_finding(pid, f2)  # same evidence_group_id="eg-1"

    ws2 = ProcessWorkspace(store)
    restored = ws2.get(pid)
    assert restored is not None
    assert len(restored.findings) == 1, "duplicate key must be deduplicated"
    assert restored.findings["eg-1"].finding_id == "f-2"
    assert restored.findings["eg-1"].finding_status is FindingStatus.CONFIRMED_VIOLATION


def test_finding_without_evidence_group_is_keyed_by_finding_id() -> None:
    """Находка без evidence_group_id (остановленная/MISSING_EVIDENCE) ключуется по finding_id."""
    store = MemoryProcessStore()
    ws1 = ProcessWorkspace(store)
    record = ws1.create("obj-3", _completeness())
    pid = record.process_id

    halted = _finding(
        finding_id="f-halt",
        evidence_group_id=None,
        status=FindingStatus.MISSING_EVIDENCE,
    )
    ws1.put_finding(pid, halted)

    ws2 = ProcessWorkspace(store)
    restored = ws2.get(pid)
    assert restored is not None
    assert "f-halt" in restored.findings
    assert restored.findings["f-halt"].finding_status is FindingStatus.MISSING_EVIDENCE


def test_findings_are_isolated_between_processes() -> None:
    """Находки одного процесса не попадают в другой."""
    store = MemoryProcessStore()
    ws1 = ProcessWorkspace(store)

    r1 = ws1.create("obj-A", _completeness())
    r2 = ws1.create("obj-B", _completeness())

    ws1.put_finding(r1.process_id, _finding(finding_id="f-A", rule_code="AR-001"))
    ws1.put_finding(
        r2.process_id,
        _finding(finding_id="f-B", rule_code="KR-002", evidence_group_id="eg-2"),
    )

    ws2 = ProcessWorkspace(store)
    rec_a = ws2.get(r1.process_id)
    rec_b = ws2.get(r2.process_id)

    assert rec_a is not None and rec_b is not None
    assert list(rec_a.findings.values())[0].rule_code == "AR-001"
    assert list(rec_b.findings.values())[0].rule_code == "KR-002"
    assert len(rec_a.findings) == 1
    assert len(rec_b.findings) == 1
