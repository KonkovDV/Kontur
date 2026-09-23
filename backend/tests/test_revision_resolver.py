"""Тесты резолвера актуальной утверждённой редакции (Gate E).

Регрессия RT-2709-08: удалите из resolve_revision проверку approved_ids —
`test_unapproved_newer_revision_does_not_become_baseline` покраснеет.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from kontur.application.revision_resolver import (
    ResolveStatus,
    RevisionConflict,
    check_stale_revision,
    resolve_heads_by_identity,
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
    document_code: str | None = None,
    sheet: str | None = None,
) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=f"sha-{file_id}",
        doc_stage=stage,
        document_code=document_code or f"CODE-{stage.value}",
        revision=file_id[-1],
        approval_status=approval,
        approval_date=approval_date,
        sheet=sheet,
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

    def test_single_unknown_pd_is_package_default(self) -> None:
        from kontur.domain.models import ApprovalBasis

        doc = _doc("pd-v1", approval=ApprovalStatus.UNKNOWN)
        result = resolve_revision([doc], DocStage.PD)
        assert result.status is ResolveStatus.RESOLVED
        assert result.resolved is not None
        assert result.resolved.document.approval_status is ApprovalStatus.APPROVED
        assert result.resolved.document.approval_basis is ApprovalBasis.PACKAGE_DEFAULT

    def test_two_unknown_pd_revisions_need_clarification(self) -> None:
        first = _doc("pd-v1", approval=ApprovalStatus.UNKNOWN, document_code="OV-1")
        second = _doc("pd-v2", approval=ApprovalStatus.UNKNOWN, document_code="OV-1")
        with pytest.raises(RevisionConflict, match="pd-v1"):
            resolve_revision([first, second], DocStage.PD)

    def test_one_inspector_choice_is_the_head(self) -> None:
        first = _doc("pd-v1")
        second = _doc("pd-v2")
        result = resolve_revision(
            [first, second],
            DocStage.PD,
            inspector_selected_file_ids=frozenset({"pd-v1"}),
        )
        assert result.status is ResolveStatus.RESOLVED
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v1"

    def test_two_inspector_choices_conflict(self) -> None:
        with pytest.raises(RevisionConflict, match="инспектор"):
            resolve_revision(
                [_doc("pd-v1"), _doc("pd-v2")],
                DocStage.PD,
                inspector_selected_file_ids=frozenset({"pd-v1", "pd-v2"}),
            )

    def test_inspector_choice_does_not_override_not_approved(self) -> None:
        from kontur.domain.models import ApprovalBasis

        rejected = _doc("pd-bad", approval=ApprovalStatus.NOT_APPROVED)
        kept = _doc("pd-ok", approval=ApprovalStatus.UNKNOWN)
        result = resolve_revision(
            [rejected, kept],
            DocStage.PD,
            inspector_selected_file_ids=frozenset({"pd-bad"}),
        )
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-ok"
        assert result.resolved.document.approval_basis is ApprovalBasis.PACKAGE_DEFAULT

    def test_rd_without_stamp_resolves(self) -> None:
        doc = _doc("rd-v1", stage=DocStage.RD, approval=ApprovalStatus.UNKNOWN)
        result = resolve_revision([doc], DocStage.RD)
        assert result.status is ResolveStatus.RESOLVED
        assert result.resolved is not None
        assert result.resolved.document.approval_status is ApprovalStatus.UNKNOWN
        assert result.resolved.document.file_id == "rd-v1"

    def test_stage_filter_ignores_other_stages(self) -> None:
        rd_doc = _doc("rd-v1", stage=DocStage.RD)
        result = resolve_revision([rd_doc], DocStage.PD)
        assert result.status is ResolveStatus.MISSING_EVIDENCE

    def test_success_is_not_a_finding_status(self) -> None:
        result = resolve_revision([_doc("pd-v1")], DocStage.PD)
        assert result.status is ResolveStatus.RESOLVED
        assert result.status.value != FindingStatus.AUTO_NO_DIFFERENCE.value

    def test_anchor_ignores_other_document_codes(self) -> None:
        pz = _doc("pd-pz", document_code="12345-PZ")
        ar = _doc("pd-ar", document_code="12345-AR")
        result = resolve_revision([pz, ar], DocStage.PD, anchor=pz)
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-pz"

    def test_distinct_ciphers_are_not_one_revision_chain(self) -> None:
        pz = _doc("pd-pz", document_code="12345-PZ")
        ar = _doc("pd-ar", document_code="12345-AR")
        with pytest.raises(RevisionConflict, match="не цепочка одного шифра"):
            resolve_revision([pz, ar], DocStage.PD)

    def test_inspector_select_does_not_supersede_another_cipher(self) -> None:
        pz = _doc("pd-pz", document_code="12345-PZ")
        ar = _doc("pd-ar", document_code="12345-AR")
        with pytest.raises(RevisionConflict, match="12345-AR"):
            resolve_revision(
                [pz, ar],
                DocStage.PD,
                inspector_selected_file_ids=frozenset({"pd-pz"}),
            )

    def test_unreadable_cipher_does_not_join_a_known_one(self) -> None:
        coded = _doc("pd-pz", document_code="12345-PZ")
        blank = replace(_doc("pd-blank"), document_code="")
        with pytest.raises(RevisionConflict, match="не прочитан"):
            resolve_revision([coded, blank], DocStage.PD)


class TestIdentityHeads:
    def test_two_ciphers_resolve_independently(self) -> None:
        pz = _doc("pd-pz", document_code="12345-PZ")
        ar = _doc("pd-ar", document_code="12345-AR")
        heads = resolve_heads_by_identity([pz, ar], DocStage.PD)
        chosen = {
            item.resolution.resolved.document.file_id
            for item in heads
            if item.resolution.resolved is not None
        }
        assert chosen == {"pd-pz", "pd-ar"}
        assert all(item.resolution.status is ResolveStatus.RESOLVED for item in heads)

    def test_inspector_select_does_not_block_other_cipher(self) -> None:
        pz = _doc("pd-pz", document_code="12345-PZ")
        ar = _doc("pd-ar", document_code="12345-AR")
        heads = resolve_heads_by_identity(
            [pz, ar],
            DocStage.PD,
            inspector_selected_file_ids=frozenset({"pd-pz"}),
        )
        chosen = {
            item.resolution.resolved.document.file_id
            for item in heads
            if item.resolution.resolved is not None
        }
        assert chosen == {"pd-pz", "pd-ar"}

    def test_blank_cipher_does_not_join_known_cipher(self) -> None:
        coded = _doc("pd-pz", document_code="12345-PZ")
        blank = replace(_doc("pd-blank"), document_code="")
        heads = resolve_heads_by_identity([coded, blank], DocStage.PD)
        assert len(heads) == 2
        assert all(item.resolution.status is ResolveStatus.RESOLVED for item in heads)


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
        assert result.resolved.is_stale is False

    def test_inspector_selected_predecessor_is_marked_stale(self) -> None:
        v1 = _doc("pd-v1", approval_date=date(2025, 1, 1), successor="pd-v2")
        v2 = _doc("pd-v2", approval_date=date(2025, 6, 1), predecessor="pd-v1")
        result = resolve_revision(
            [v1, v2],
            DocStage.PD,
            inspector_selected_file_ids=frozenset({"pd-v1"}),
        )
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v1"
        assert result.resolved.is_stale is True

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

    def test_unknown_successor_becomes_package_default_head(self) -> None:
        from kontur.domain.models import ApprovalBasis

        v1 = _doc("pd-v1", approval=ApprovalStatus.APPROVED, successor="pd-v2")
        v2 = _doc("pd-v2", approval=ApprovalStatus.UNKNOWN, predecessor="pd-v1")
        result = resolve_revision([v1, v2], DocStage.PD)
        assert result.resolved is not None
        assert result.resolved.document.file_id == "pd-v2"
        assert result.resolved.document.approval_basis is ApprovalBasis.PACKAGE_DEFAULT

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


def test_inspector_select_records_basis_only_when_stamp_is_unproven() -> None:
    from kontur.application.revision_resolver import approval_with_basis
    from kontur.domain.models import ApprovalBasis

    status, basis = approval_with_basis(
        ApprovalStatus.UNKNOWN,
        ApprovalBasis.UNPROVEN,
        inspector_selected=True,
    )
    assert status is ApprovalStatus.APPROVED
    assert basis is ApprovalBasis.INSPECTOR_SELECT
    status, basis = approval_with_basis(
        ApprovalStatus.APPROVED,
        ApprovalBasis.TITLE_BLOCK,
        inspector_selected=True,
    )
    assert status is ApprovalStatus.APPROVED
    assert basis is ApprovalBasis.TITLE_BLOCK
    status, basis = approval_with_basis(
        ApprovalStatus.NOT_APPROVED,
        ApprovalBasis.TITLE_BLOCK,
        inspector_selected=True,
    )
    assert status is ApprovalStatus.NOT_APPROVED
    assert basis is ApprovalBasis.TITLE_BLOCK


def test_inspector_overlay_does_not_override_not_approved() -> None:
    from kontur.application.revision_resolver import overlay_inspector_approval

    assert (
        overlay_inspector_approval(ApprovalStatus.NOT_APPROVED, inspector_selected=True)
        is ApprovalStatus.NOT_APPROVED
    )
    assert (
        overlay_inspector_approval(ApprovalStatus.UNKNOWN, inspector_selected=True)
        is ApprovalStatus.APPROVED
    )
    assert (
        overlay_inspector_approval(ApprovalStatus.UNKNOWN, inspector_selected=False)
        is ApprovalStatus.UNKNOWN
    )
    assert (
        overlay_inspector_approval(ApprovalStatus.APPROVED, inspector_selected=False)
        is ApprovalStatus.APPROVED
    )

