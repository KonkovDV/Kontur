"""Марка установки: подозрение с доказательством, не попадание скоринга."""

from __future__ import annotations

from kontur.application.element_match import ventilation_element_suspicion
from kontur.application.extractors.number import PageToken
from kontur.application.suspicion import SuspicionApproach
from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus, ReviewPriority
from kontur.evaluation.train_public import is_predicted_positive


def _tok(text: str, x: float) -> PageToken:
    polygon = ((x, 0.40), (x + 0.08, 0.40), (x + 0.08, 0.44), (x, 0.44))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def test_same_label_in_the_same_place_is_silent() -> None:
    tokens = (_tok("П1", 0.20),)
    assert (
        ventilation_element_suspicion(
            tokens, tokens, rule_code="IOS4-079", evidence_group_id="eg-1"
        )
        is None
    )


def test_label_on_one_side_is_suspicion_not_a_hit() -> None:
    signal = ventilation_element_suspicion(
        (_tok("В1", 0.20),),
        (_tok("план", 0.20),),
        rule_code="IOS4-079",
        evidence_group_id="eg-vent",
    )
    assert signal is not None
    assert signal.status is FindingStatus.SUSPICION
    assert signal.approach is SuspicionApproach.PARTIAL_MATCH
    assert signal.evidence_group_id == "eg-vent"
    assert is_predicted_positive(signal.status) is False
    finding = Finding(
        finding_id="f-vent",
        rule_code="IOS4-079",
        finding_status=signal.status,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=signal.evidence_group_id,
        rationale=signal.detail,
    )
    assert is_predicted_positive(finding.finding_status) is False
    assert "В1" in signal.detail


def test_same_label_far_apart_is_suspicion() -> None:
    signal = ventilation_element_suspicion(
        (_tok("П-1", 0.10),),
        (_tok("П1", 0.70),),
        rule_code="IOS4-079",
        evidence_group_id="eg-far",
    )
    assert signal is not None
    assert signal.status is FindingStatus.SUSPICION
    assert is_predicted_positive(signal.status) is False
    assert "перекрытие" in signal.detail


def test_repeated_label_is_an_annotation_conflict() -> None:
    signal = ventilation_element_suspicion(
        (_tok("П1", 0.10), _tok("П1", 0.50)),
        (_tok("П1", 0.10),),
        rule_code="IOS4-079",
        evidence_group_id="eg-dup",
    )
    assert signal is not None
    assert signal.approach is SuspicionApproach.ANNOTATION_CONFLICT
    assert is_predicted_positive(signal.status) is False
