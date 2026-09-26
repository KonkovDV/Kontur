"""Отказы среза 27.09. Геометрия, контур, ведомость и вентиляция не сравнивают
неутверждённую ПД и две головы одного шифра. Автомат не пишет CONFIRMED_VIOLATION.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "e" * 64
OBJECT_ID = "OBJ-SLICE-REFUSAL"
_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str) -> PageToken:
    polygon = ((0.10, 0.40), (0.20, 0.40), (0.20, 0.44), (0.10, 0.44))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _doc(
    stage: DocStage,
    *,
    file_id: str,
    code: str,
    approval: ApprovalStatus = ApprovalStatus.APPROVED,
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


def _pages(pd: DocumentRef, rd: DocumentRef) -> dict[DocStage, StagePage | tuple[StagePage, ...]]:
    return {
        DocStage.PD: StagePage(document=pd, tokens=(_tok("лист"),)),
        DocStage.RD: StagePage(document=rd, tokens=(_tok("лист"),)),
    }


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


@pytest.mark.parametrize(
    ("code", "cipher"),
    [
        ("AR-040", "11111-AR"),
        ("SPZU-025", "11111-SPZU"),
        ("IOS2-071", "ИОС2-1"),
        ("IOS4-078", "ОВ-1"),
        ("IOS4-079", "ОВ-1"),
    ],
)
def test_unapproved_pd_and_two_heads_are_not_candidates(code: str, cipher: str) -> None:
    rule = _REGISTRY.get(code)
    blocked = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=_pages(
            _doc(DocStage.PD, file_id="pd", code=cipher, approval=ApprovalStatus.NOT_APPROVED),
            _doc(DocStage.RD, file_id="rd", code=f"{cipher}-RD"),
        ),
        completeness=_completeness(),
    )
    assert blocked.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert blocked.finding.finding_status is not FindingStatus.CANDIDATE
    first = _doc(DocStage.PD, file_id="pd-a", code=cipher)
    second = replace(first, file_id="pd-b")
    rd = _doc(DocStage.RD, file_id="rd", code=f"{cipher}-RD")
    conflict = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: (
                StagePage(document=first, tokens=(_tok("лист"),)),
                StagePage(document=second, tokens=(_tok("лист"),)),
            ),
            DocStage.RD: StagePage(document=rd, tokens=(_tok("лист"),)),
        },
        completeness=_completeness(),
        revision_pool=[first, second, rd],
    )
    assert conflict.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert conflict.finding.finding_status is not FindingStatus.CANDIDATE
    assert conflict.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
