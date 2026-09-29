"""Единственная голова ПД без штампа сравнивается. Две головы и «не утв.» нет.

Автомат не пишет CONFIRMED_VIOLATION. strict повторяет ADR-0015.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.protocol_export import cards_from_groups
from kontur.application.revision_resolver import SOLE_HEAD_NOTICE
from kontur.domain.models import (
    ApprovalBasis,
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Extraction,
    ExtractionEngine,
)
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "e" * 64
OBJECT_ID = "OBJ-SOLE-HEAD"
_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str) -> PageToken:
    polygon = ((0.10, 0.40), (0.20, 0.40), (0.20, 0.44), (0.10, 0.44))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _doc(
    stage: DocStage,
    *,
    file_id: str,
    code: str,
    approval: ApprovalStatus = ApprovalStatus.UNKNOWN,
) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=HASH,
        doc_stage=stage,
        document_code=code,
        revision="1",
        approval_status=approval,
        sheet="1",
    )


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def test_one_unknown_pd_compares(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KONTUR_ETALON_POLICY", raising=False)
    pd = _doc(DocStage.PD, file_id="pd", code="11111-PZ")
    rd = _doc(DocStage.RD, file_id="rd", code="11111-PZ-RD", approval=ApprovalStatus.UNKNOWN)
    result = evaluate_rule(
        _REGISTRY.get("PZ-001"),
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: StagePage(document=pd, tokens=(_tok("лист"),)),
            DocStage.RD: StagePage(document=rd, tokens=(_tok("лист"),)),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is not FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert "утверждени" not in result.finding.rationale


def test_strict_unknown_pd_stays_clarification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTUR_ETALON_POLICY", "strict")
    pd = _doc(DocStage.PD, file_id="pd", code="11111-PZ")
    rd = _doc(DocStage.RD, file_id="rd", code="11111-PZ-RD")
    result = evaluate_rule(
        _REGISTRY.get("PZ-001"),
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: StagePage(document=pd, tokens=(_tok("лист"),)),
            DocStage.RD: StagePage(document=rd, tokens=(_tok("лист"),)),
        },
        completeness=_completeness(),
        revision_pool=[pd, rd],
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.rationale == "сведения об утверждении отсутствуют"
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION


def test_stamped_blank_does_not_drop_another_volume() -> None:
    from kontur.application.process_pipeline import _stages_from_heads
    from kontur.domain.models import ApprovalBasis

    stamped = _doc(DocStage.PD, file_id="pz", code="", approval=ApprovalStatus.APPROVED)
    stamped = replace(stamped, approval_basis=ApprovalBasis.TITLE_BLOCK, file_hash="a" * 64)
    other = _doc(DocStage.PD, file_id="ov", code="Том 5.4.2 ОВ")
    other = replace(other, file_hash="b" * 64)
    draft = _doc(DocStage.PD, file_id="draft", code="")
    draft = replace(draft, file_hash="c" * 64)
    rd = _doc(DocStage.RD, file_id="rd", code="", approval=ApprovalStatus.UNKNOWN)
    rd = replace(rd, file_hash="d" * 64)
    built = [
        (stamped, StagePage(document=stamped, tokens=())),
        (other, StagePage(document=other, tokens=())),
        (draft, StagePage(document=draft, tokens=())),
        (rd, StagePage(document=rd, tokens=())),
    ]
    raw = _stages_from_heads(built, frozenset())[DocStage.PD]
    assert isinstance(raw, tuple)
    assert {page.document.file_id for page in raw} == {"pz", "ov", "draft"}
    chosen_pages = _stages_from_heads(built, frozenset({"pz"}))
    assert chosen_pages[DocStage.RD].document.file_id == "rd"
    chosen = chosen_pages[DocStage.PD]
    assert isinstance(chosen, tuple)
    by_id = {page.document.file_id: page.document for page in chosen}
    assert set(by_id) == {"pz", "ov"}
    assert by_id["ov"].approval_basis is ApprovalBasis.SOLE_HEAD
    assert by_id["ov"].approval_status is ApprovalStatus.UNKNOWN
    assert by_id["pz"].approval_status is ApprovalStatus.APPROVED


def test_protocol_names_the_unproven_stamp() -> None:
    polygon = ((0.1, 0.2), (0.4, 0.2), (0.4, 0.3), (0.1, 0.3))
    area = "1250"
    expected = replace(
        _doc(DocStage.PD, file_id="pd", code="11111-PZ"),
        approval_basis=ApprovalBasis.SOLE_HEAD,
    )
    actual = _doc(DocStage.RD, file_id="rd", code="11111-PZ-RD")

    def _fragment(fragment_id: str, role: EvidenceRole, document: DocumentRef) -> EvidenceFragment:
        return EvidenceFragment(
            fragment_id=fragment_id,
            role=role,
            document=document,
            page=1,
            polygon_source=((72.0, 400.0), (200.0, 400.0), (200.0, 430.0), (72.0, 430.0)),
            polygon_norm=polygon,
            extracted=Extraction(
                raw_token=area,
                engine=ExtractionEngine.VECTOR,
                engine_version="pdfium",
                confidence=0.9,
                grounded_in_source_tokens=True,
            ),
        )

    group = EvidenceGroup(
        evidence_group_id="eg-1",
        object_id=OBJECT_ID,
        rule_code="PZ-001",
        matrix_version="draft-0",
        fragments=(
            _fragment("eg-1-PD", EvidenceRole.EXPECTED, expected),
            _fragment("eg-1-RD", EvidenceRole.ACTUAL, actual),
        ),
    )
    cards = cards_from_groups(
        {
            "sections": {
                "candidates": [
                    {"finding_id": "f-1", "evidence_group_id": "eg-1", "rule_code": "PZ-001"}
                ]
            }
        },
        {"eg-1": group},
    )
    assert SOLE_HEAD_NOTICE in cards["f-1"]["approval_basis"]
