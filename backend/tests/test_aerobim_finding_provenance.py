"""Tests: Finding provenance (source_id, evidence_refs, DisagreementKind).

Donor: AeroBIM source_id + evidence_refs pattern.
Gate K: ≤3-click traceability — inspector must be able to jump to the source.
"""

from __future__ import annotations

import warnings

import pytest

from kontur.domain.models import DocStage, EvidenceRole, Finding
from kontur.domain.provenance import DisagreementKind, EvidenceRef, SourceRef
from kontur.domain.statuses import FindingStatus, ReviewPriority


def _minimal_finding(**kwargs: object) -> Finding:
    base: dict[str, object] = {
        "finding_id": "f-001",
        "rule_code": "IOS4-078",
        "finding_status": FindingStatus.CANDIDATE,
        "review_priority": ReviewPriority.HIGH,
        "matrix_version": "1.0",
        "rule_version": "1.0",
        "model_version": "1.0",
    }
    base.update(kwargs)
    return Finding(**base)  # type: ignore[arg-type]


class TestSourceRef:
    def test_source_ref_round_trip(self) -> None:
        ref = SourceRef(
            fragment_id="frag-abc",
            doc_stage=DocStage.PD,
            page=12,
            polygon_source=((10.0, 20.0), (100.0, 20.0), (100.0, 40.0), (10.0, 40.0)),
            locator_hint="Таблица 3 — Воздуховоды",
        )
        assert ref.fragment_id == "frag-abc"
        assert ref.doc_stage is DocStage.PD
        assert ref.page == 12

    def test_source_ref_rejects_zero_page(self) -> None:
        with pytest.raises(ValueError, match="≥ 1"):
            SourceRef(
                fragment_id="f",
                doc_stage=DocStage.PD,
                page=0,
                polygon_source=(),
            )


class TestEvidenceRef:
    def test_evidence_ref_round_trip(self) -> None:
        ref = EvidenceRef(
            fragment_id="frag-abc",
            role=EvidenceRole.EXPECTED,
            doc_stage=DocStage.PD,
            page=5,
        )
        assert ref.role is EvidenceRole.EXPECTED


class TestDisagreementKind:
    def test_all_kinds_accessible(self) -> None:
        assert DisagreementKind.VALUE_DELTA.value == "value_delta"
        assert DisagreementKind.MISSING_IN_STAGE.value == "missing_in_stage"
        assert DisagreementKind.AMBIGUOUS_REFERENCE.value == "ambiguous_reference"
        assert DisagreementKind.FORMAT_MISMATCH.value == "format_mismatch"

    def test_ios4_078_disagreement_kind(self) -> None:
        # IOS4-078: воздуховод 600×300 в ПД → 400×250 в РД → VALUE_DELTA
        kind = DisagreementKind.VALUE_DELTA
        finding = _minimal_finding(
            rule_code="IOS4-078",
            disagreement_kind=kind.value,
            expected_value="600x300",
            actual_value="400x250",
        )
        assert finding.disagreement_kind == "value_delta"


class TestFindingProvenance:
    def test_finding_with_source_id_no_warning(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning → error
            finding = _minimal_finding(
                evidence_group_id="eg-001",
                source_id="pd:page12:frag-abc",
            )
        assert finding.source_id == "pd:page12:frag-abc"

    def test_finding_with_evidence_group_but_no_source_id_warns(self) -> None:
        with pytest.warns(UserWarning, match="source_id is None"):
            finding = _minimal_finding(
                evidence_group_id="eg-001",
                source_id=None,  # explicit None → Gate K degraded
            )
        assert finding.evidence_group_id == "eg-001"
        assert finding.source_id is None

    def test_finding_without_evidence_no_warning(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            finding = _minimal_finding()  # no evidence_group_id
        assert finding.source_id is None

    def test_evidence_refs_stored(self) -> None:
        ref = EvidenceRef(
            fragment_id="frag-xyz",
            role=EvidenceRole.ACTUAL,
            doc_stage=DocStage.RD,
            page=3,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            finding = _minimal_finding(
                evidence_group_id="eg-002",
                evidence_refs=(ref,),
            )
        assert len(finding.evidence_refs) == 1
        assert finding.evidence_refs[0].fragment_id == "frag-xyz"
