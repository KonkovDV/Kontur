"""SOTA-K3: parameter diff between revisions of a document."""

from __future__ import annotations

import hashlib

import pytest

from kontur.application.revision_diff import ChangeKind, RevisionChainError, diff_revisions
from kontur.domain.models import (
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Extraction,
    ExtractionEngine,
)

TRIANGLE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))


def _doc(file_id: str, revision: str, predecessor: str | None = None) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=hashlib.sha256(file_id.encode()).hexdigest(),
        doc_stage=DocStage.PD,
        document_code="ПЗ",
        revision=revision,
        approval_status=ApprovalStatus.APPROVED,
        predecessor_file_id=predecessor,
    )


OLD = _doc("f1", "0")
NEW = _doc("f2", "1", predecessor="f1")
OTHER = _doc("f9", "0")


def _frag(
    fid: str,
    doc: DocumentRef,
    value: float,
    *,
    unit: str = "м²",
    page: int = 1,
    grounded: bool = True,
    role: EvidenceRole = EvidenceRole.ACTUAL,
) -> EvidenceFragment:
    return EvidenceFragment(
        fragment_id=fid,
        role=role,
        document=doc,
        page=page,
        polygon_source=TRIANGLE,
        polygon_norm=TRIANGLE,
        extracted=Extraction(
            raw_token=str(value),
            engine=ExtractionEngine.VECTOR,
            engine_version="t",
            confidence=1.0,
            normalized_value=value,
            unit=unit,
            grounded_in_source_tokens=grounded,
        ),
    )


def _group(code: str, *fragments: EvidenceFragment) -> EvidenceGroup:
    anchor = _frag(f"{code}-e", OTHER, 0.0, role=EvidenceRole.EXPECTED)
    return EvidenceGroup(f"g-{code}", "obj", code, "draft-0", (anchor, *fragments))


def _kinds(groups: list[EvidenceGroup]) -> dict[str, ChangeKind]:
    return {c.rule_code: c.kind for c in diff_revisions(groups, OLD, NEW)}


def test_changed_unchanged_added_removed() -> None:
    groups = [
        _group("PZ-001", _frag("a", OLD, 100.0), _frag("b", NEW, 120.0)),
        _group("PZ-002", _frag("c", OLD, 5.0), _frag("d", NEW, 5.0)),
        _group("PZ-003", _frag("e", NEW, 7.0)),
        _group("PZ-004", _frag("f", OLD, 9.0)),
    ]
    assert _kinds(groups) == {
        "PZ-001": ChangeKind.CHANGED,
        "PZ-002": ChangeKind.UNCHANGED,
        "PZ-003": ChangeKind.ADDED,
        "PZ-004": ChangeKind.REMOVED,
    }


def test_unit_change_is_a_change_without_conversion() -> None:
    groups = [_group("PZ-001", _frag("a", OLD, 1.0, unit="га"), _frag("b", NEW, 1.0))]
    assert _kinds(groups)["PZ-001"] is ChangeKind.CHANGED


def test_conflicting_values_in_one_revision_are_ambiguous() -> None:
    groups = [
        _group("PZ-001", _frag("a", OLD, 1.0), _frag("b", OLD, 2.0, page=2), _frag("c", NEW, 1.0))
    ]
    assert _kinds(groups)["PZ-001"] is ChangeKind.AMBIGUOUS


def test_ungrounded_value_is_not_usable_for_automatic_finding() -> None:
    groups = [_group("PZ-001", _frag("a", OLD, 1.0), _frag("b", NEW, 2.0, grounded=False))]
    (change,) = [c for c in diff_revisions(groups, OLD, NEW) if c.rule_code == "PZ-001"]
    assert change.kind is ChangeKind.CHANGED
    assert change.usable_for_automatic_finding is False


def test_revision_order_is_never_guessed() -> None:
    with pytest.raises(RevisionChainError):
        diff_revisions([], NEW, OLD)
    with pytest.raises(RevisionChainError):
        diff_revisions([], OLD, _doc("f3", "2"))


def test_protocol_payload_lists_changed_pairs_and_rin_drops_them() -> None:
    from kontur.application.protocol import protocol_for_rin
    from kontur.application.revision_diff import revision_changes

    groups = [
        _group("PZ-002", _frag("a", OLD, 10.0), _frag("b", NEW, 12.0)),
        _group("PZ-003", _frag("c", OLD, 5.0), _frag("d", NEW, 5.0)),
    ]
    (pair,) = revision_changes(groups)
    assert [c["rule_code"] for c in pair["changes"]] == ["PZ-002"]  # type: ignore[union-attr]
    assert revision_changes(groups[1:]) == []
    rin = protocol_for_rin({"sections": {}, "revision_changes": [pair]})
    assert "revision_changes" not in rin
