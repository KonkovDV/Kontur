"""Family extractor fixtures for issue #82.

These fixtures prove the family mechanics only. They do not promote production
matrix rules to executable coverage or close Gate J.
"""

from __future__ import annotations

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.extractors.text import extract_exact_field, extract_presence
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.statuses import Completeness, FindingStatus

HASH = "a" * 64
OBJECT_ID = "OBJ-FAMILY-FIXTURE"


def _token(text: str, x: float) -> PageToken:
    polygon = ((x, 0.4), (x + 0.1, 0.4), (x + 0.1, 0.45), (x, 0.45))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _page(stage: DocStage, *words: str) -> StagePage:
    return StagePage(
        document=DocumentRef(
            file_id=f"family-{stage.value.lower()}",
            file_hash=HASH,
            doc_stage=stage,
            document_code="FAMILY-FIXTURE",
            revision="1",
            approval_status=ApprovalStatus.APPROVED,
        ),
        tokens=tuple(_token(word, 0.05 + i * 0.12) for i, word in enumerate(words)),
    )


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def _exact_rule() -> dict[str, object]:
    return {
        "code": "FIXTURE-EXACT-FIELD",
        "matrix_version": "fixture-1",
        "unit": "—",
        "extractor": {
            "type": "exact_field",
            "regex": r"(наружу|внутрь)",
            "anchors": ["Направление открывания"],
            "normalization": ["nfc", "collapse_spaces", "lower"],
            "dual_read_required": False,
        },
        "comparator": {"operator": "eq"},
        "failure_mapping": {
            "source_absent": "MISSING_EVIDENCE",
            "low_quality": "LOW_QUALITY",
            "reads_disagree": "ABSTAIN",
            "revision_conflict": "CLARIFICATION_REQUIRED",
            "not_comparable": "NOT_COMPARABLE",
        },
        "review_priority": "HIGH",
    }


def _presence_rule() -> dict[str, object]:
    return {
        "code": "FIXTURE-PRESENCE",
        "matrix_version": "fixture-1",
        "unit": "—",
        "extractor": {
            "type": "presence",
            "regex": None,
            "anchors": ["Демпферная лента"],
            "normalization": ["nfc", "collapse_spaces"],
            "dual_read_required": False,
        },
        "comparator": {"operator": "present"},
        "failure_mapping": {
            "source_absent": "MISSING_EVIDENCE",
            "low_quality": "LOW_QUALITY",
            "reads_disagree": "ABSTAIN",
            "revision_conflict": "CLARIFICATION_REQUIRED",
            "not_comparable": "NOT_COMPARABLE",
        },
        "review_priority": "MEDIUM",
    }


def test_exact_field_extractor_requires_explicit_value_pattern() -> None:
    rule = _exact_rule()
    assert extract_exact_field(
        _page(DocStage.RD, "Направление", "открывания", "наружу").tokens,
        rule,
    ) is not None
    rule["extractor"]["regex"] = None  # type: ignore[index]
    assert extract_exact_field(
        _page(DocStage.RD, "Направление", "открывания", "наружу").tokens,
        rule,
    ) is None


def test_exact_field_equal_values_are_auto_no_difference() -> None:
    rule = _exact_rule()
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, "Направление", "открывания", "наружу"),
            DocStage.RD: _page(DocStage.RD, "Направление", "открывания", "наружу"),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.finding.evidence_group_id is not None
    assert result.evidence_group is not None
    assert len(result.evidence_group.fragments) == 2


def test_exact_field_difference_is_candidate_with_provenance() -> None:
    rule = _exact_rule()
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, "Направление", "открывания", "наружу"),
            DocStage.RD: _page(DocStage.RD, "Направление", "открывания", "внутрь"),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.CANDIDATE
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.source_id == "family-pd"
    assert result.evidence_group is not None
    assert all(fragment.document.file_hash == HASH for fragment in result.evidence_group.fragments)


def test_presence_requires_positive_anchor_and_never_guesses_absence() -> None:
    rule = _presence_rule()
    tokens = _page(DocStage.RD, "Демпферная", "лента").tokens
    hit = extract_presence(tokens, rule)
    assert hit is not None
    assert hit.extraction.normalized_value is True
    absent = _page(DocStage.RD, "Прокладка", "перекрытия").tokens
    assert extract_presence(absent, rule) is None

    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, "Демпферная", "лента"),
            DocStage.RD: _page(DocStage.RD, "Прокладка", "перекрытия"),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert result.finding.finding_status is not FindingStatus.CANDIDATE
    assert result.evidence_group is None


def test_presence_on_both_stages_is_auto_no_difference() -> None:
    result = evaluate_rule(
        _presence_rule(),
        object_id=OBJECT_ID,
        pages={
            DocStage.PD: _page(DocStage.PD, "Демпферная", "лента"),
            DocStage.RD: _page(DocStage.RD, "Демпферная", "лента"),
        },
        completeness=_completeness(),
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert result.evidence_group is not None
