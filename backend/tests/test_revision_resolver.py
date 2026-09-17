"""Тесты резолвера актуальной утверждённой редакции (Gate E).

Регрессия RT-2709-08: удалите из resolve_revision проверку approved_ids —
`test_unapproved_newer_revision_does_not_become_baseline` покраснеет.
"""

from __future__ import annotations

from datetime import date

import pytest

from kontur.application.revision_resolver import (
    ResolveStatus,
    RevisionConflict,
    check_stale_revision,
    resolve_revision,
)
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import FindingStatus


def _doc(
    file_id: str,
    *,
    stage: DocStage = DocStage.PD,
    approval: ApprovalStatus = ApprovalStatus.APPROVED,
    approval_date: date | None = None,
    predecessor: str | None = None,
    successor: str | None = None,
) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=f"sha-{file_id}",
        doc_stage=stage,
        document_code=f"CODE-{file_id}",
        revision=file_id[-1],
        approval_status=approval,
        approval_date=approval_date,
        predecessor_file_id=predecessor,
        successor_file_id=successor,
    )


# ---------------------------------------------------------------------------
# Базовые случаи
# ---------------------------------------------------------------------------

class TestBasicResolution:
    def test_single_approved_is_resolved(self) -> None:
        doc = _doc("pd-v1")
        result = resolve_revision([doc], DocStage.PD)
        assert result.status is ResolveStatus.RESOLVED
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v1"

    def test_no_documents_gives_missing_evidence(self) -> None:
        result = resolve_revision([], DocStage.PD)
        assert result.status is ResolveStatus.MISSING_EVIDENCE
        assert result.resolved is None

    def test_no_approved_gives_clarification_required(self) -> None:
        doc = _doc("pd-v1", approval=ApprovalStatus.NOT_APPROVED)
        result = resolve_revision([doc], DocStage.PD)
        assert result.status is ResolveStatus.CLARIFICATION_REQUIRED
        assert result.resolved is None

    def test_unknown_approval_gives_clarification_required(self) -> None:
        doc = _doc("pd-v1", approval=ApprovalStatus.UNKNOWN)
        result = resolve_revision([doc], DocStage.PD)
        assert result.status is ResolveStatus.CLARIFICATION_REQUIRED

    def test_stage_filter_ignores_other_stages(self) -> None:
        rd_doc = _doc("rd-v1", stage=DocStage.RD)
        result = resolve_revision([rd_doc], DocStage.PD)
        assert result.status is ResolveStatus.MISSING_EVIDENCE

    def test_success_is_not_a_finding_status(self) -> None:
        result = resolve_revision([_doc("pd-v1")], DocStage.PD)
        assert result.status is ResolveStatus.RESOLVED
        assert result.status.value != FindingStatus.AUTO_NO_DIFFERENCE.value


# ---------------------------------------------------------------------------
# Цепочки редакций
# ---------------------------------------------------------------------------

class TestRevisionChain:
    def test_successor_chain_picks_head(self) -> None:
        """v2 — голова цепочки: approved, нет successor."""
        v1 = _doc("pd-v1", approval_date=date(2025, 1, 1), successor="pd-v2")
        v2 = _doc("pd-v2", approval_date=date(2025, 6, 1), predecessor="pd-v1")
        result = resolve_revision([v1, v2], DocStage.PD)
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v2"

    def test_unapproved_newer_revision_does_not_become_baseline(self) -> None:
        """RT-2709-08: неутверждённая редакция, даже новее, не эталон.

        Цепочка явная: v1.successor = v2. Если убрать фильтр APPROVED, голова
        станет v2.
        """
        v1 = _doc(
            "pd-v1",
            approval=ApprovalStatus.APPROVED,
            approval_date=date(2025, 1, 1),
            successor="pd-v2",
        )
        v2 = _doc(
            "pd-v2",
            approval=ApprovalStatus.NOT_APPROVED,
            approval_date=date(2025, 9, 1),
            predecessor="pd-v1",
        )
        result = resolve_revision([v1, v2], DocStage.PD)
        assert result.status is ResolveStatus.RESOLVED
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v1"

    def test_unknown_approval_also_does_not_become_baseline(self) -> None:
        v1 = _doc("pd-v1", approval=ApprovalStatus.APPROVED, successor="pd-v2")
        v2 = _doc("pd-v2", approval=ApprovalStatus.UNKNOWN, predecessor="pd-v1")
        result = resolve_revision([v1, v2], DocStage.PD)
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v1"

    def test_three_version_chain_resolves_to_latest(self) -> None:
        v1 = _doc("pd-v1", approval_date=date(2024, 1, 1), successor="pd-v2")
        v2 = _doc(
            "pd-v2",
            approval_date=date(2024, 6, 1),
            predecessor="pd-v1",
            successor="pd-v3",
        )
        v3 = _doc("pd-v3", approval_date=date(2025, 1, 1), predecessor="pd-v2")
        result = resolve_revision([v1, v2, v3], DocStage.PD)
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v3"


# ---------------------------------------------------------------------------
# Конфликты
# ---------------------------------------------------------------------------

class TestConflicts:
    def test_two_approved_without_successor_raises(self) -> None:
        """Два approved без successor — неразрешимый конфликт."""
        v1 = _doc("pd-v1")
        v2 = _doc("pd-v2")
        with pytest.raises(RevisionConflict):
            resolve_revision([v1, v2], DocStage.PD)

    def test_conflict_message_contains_file_ids(self) -> None:
        v1 = _doc("pd-alpha")
        v2 = _doc("pd-beta")
        with pytest.raises(RevisionConflict, match="pd-alpha"):
            resolve_revision([v1, v2], DocStage.PD)

    def test_cycle_raises(self) -> None:
        v1 = _doc("pd-v1", successor="pd-v2")
        v2 = _doc("pd-v2", predecessor="pd-v1", successor="pd-v1")
        with pytest.raises(RevisionConflict, match="цикл"):
            resolve_revision([v1, v2], DocStage.PD)


# ---------------------------------------------------------------------------
# Проверка устаревших документов (FPR-контроль)
# ---------------------------------------------------------------------------

class TestStaleRevision:
    def test_stale_returns_true_when_superseded(self) -> None:
        old = _doc("pd-v1", approval_date=date(2025, 1, 1))
        new = _doc("pd-v2", approval_date=date(2025, 6, 1), predecessor="pd-v1")
        assert check_stale_revision(old, [old, new]) is True

    def test_current_head_is_not_stale(self) -> None:
        old = _doc("pd-v1", approval_date=date(2025, 1, 1))
        new = _doc("pd-v2", approval_date=date(2025, 6, 1), predecessor="pd-v1")
        assert check_stale_revision(new, [old, new]) is False

    def test_unapproved_successor_does_not_make_predecessor_stale(self) -> None:
        """Неутверждённый successor не устаревляет predecessor."""
        old = _doc(
            "pd-v1",
            approval=ApprovalStatus.APPROVED,
            approval_date=date(2025, 1, 1),
        )
        draft = _doc(
            "pd-v2",
            approval=ApprovalStatus.NOT_APPROVED,
            approval_date=date(2025, 9, 1),
            predecessor="pd-v1",
        )
        assert check_stale_revision(old, [old, draft]) is False

    def test_solo_document_is_not_stale(self) -> None:
        doc = _doc("pd-v1", approval_date=date(2025, 1, 1))
        assert check_stale_revision(doc, [doc]) is False
