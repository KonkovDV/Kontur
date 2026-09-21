"""Адаптер submission_schema: внутренний статус ≠ метка хакатона, JSON собирается один раз."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from kontur.domain.models import (
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Extraction,
    ExtractionEngine,
    Finding,
)
from kontur.domain.statuses import WIRE_FINDING_STATUSES, FindingStatus, ReviewPriority
from kontur.evaluation.submission import (
    ContestCodeStyle,
    ContestProtocolStatus,
    ContestViolationLabel,
    build_check,
    build_submission,
    contest_allows_auto_no_difference,
    contest_parameter_code,
    contest_protocol_status,
    contest_violation_label,
    findings_to_submission,
)

SUBMISSION_SCHEMA = (
    Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "submission.schema.json"
)
SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


def _fragment(
    role: EvidenceRole,
    stage: DocStage,
    *,
    value: str = "12.5",
    page: int = 7,
    grounded: bool = True,
    second_read: bool | None = None,
) -> EvidenceFragment:
    return EvidenceFragment(
        fragment_id=f"frag-{role.value}-{stage.value}",
        role=role,
        document=DocumentRef(
            file_id=f"file-{stage.value.lower()}",
            file_hash="a" * 64,
            doc_stage=stage,
            document_code=f"12345-{stage.value}",
            revision="2",
            approval_status=ApprovalStatus.APPROVED,
            sheet="7",
        ),
        page=page,
        polygon_source=SQUARE,
        polygon_norm=SQUARE,
        extracted=Extraction(
            raw_token=value,
            engine=ExtractionEngine.VECTOR,
            engine_version="pdfium-4.30",
            confidence=0.98,
            normalized_value=value,
            grounded_in_source_tokens=grounded,
            second_read_agrees=second_read,
        ),
    )


def _group(
    *fragments: EvidenceFragment,
    rule_code: str = "AR-014",
    group_id: str = "eg-1",
) -> EvidenceGroup:
    return EvidenceGroup(
        evidence_group_id=group_id,
        object_id="obj-1",
        rule_code=rule_code,
        matrix_version="draft-0",
        fragments=fragments,
    )


def _finding(
    status: FindingStatus = FindingStatus.CANDIDATE,
    *,
    rule_code: str = "AR-014",
    group_id: str | None = "eg-1",
    priority: ReviewPriority = ReviewPriority.HIGH,
) -> Finding:
    return Finding(
        finding_id="fnd-1",
        rule_code=rule_code,
        finding_status=status,
        review_priority=priority,
        matrix_version="draft-0",
        rule_version="1",
        model_version="m-0",
        evidence_group_id=group_id,
    )


def test_two_wires_diverge_on_auto_no_difference() -> None:
    assert contest_allows_auto_no_difference()
    assert FindingStatus.AUTO_NO_DIFFERENCE not in WIRE_FINDING_STATUSES
    assert (
        contest_violation_label(FindingStatus.AUTO_NO_DIFFERENCE)
        is ContestViolationLabel.NO_VIOLATION
    )


def test_candidate_is_contest_detection_not_confirmed_violation() -> None:
    assert (
        contest_violation_label(FindingStatus.CANDIDATE)
        is ContestViolationLabel.VIOLATION_PRESENT
    )
    assert FindingStatus.CANDIDATE in WIRE_FINDING_STATUSES


def test_human_only_statuses_map_without_rewriting_domain() -> None:
    assert (
        contest_violation_label(FindingStatus.CONFIRMED_VIOLATION)
        is ContestViolationLabel.VIOLATION_PRESENT
    )
    assert (
        contest_violation_label(FindingStatus.NEGATIVE_VERIFIED)
        is ContestViolationLabel.NO_VIOLATION
    )


def test_data_quality_does_not_become_a_violation_on_contest_wire() -> None:
    assert (
        contest_violation_label(FindingStatus.MISSING_EVIDENCE)
        is ContestViolationLabel.MISSING_DOCUMENT
    )
    assert (
        contest_violation_label(FindingStatus.ABSTAIN)
        is ContestViolationLabel.COMPARISON_IMPOSSIBLE
    )
    assert (
        contest_violation_label(FindingStatus.SUSPICION)
        is ContestViolationLabel.COMPARISON_IMPOSSIBLE
    )


def test_every_finding_status_has_contest_mapping() -> None:
    for status in FindingStatus:
        assert isinstance(contest_violation_label(status), ContestViolationLabel)


def test_parameter_code_is_normalized_before_it_reaches_the_wire() -> None:
    """Короткая форма и типографский дефис из PDF не должны уехать в ответ как есть."""

    assert contest_parameter_code("ar\u201114") == "AR-014"
    assert contest_parameter_code("PZ-1") == "PZ-001"
    assert contest_parameter_code("PZ-1", ContestCodeStyle.SHORT) == "PZ-1"
    with pytest.raises(ValueError):
        contest_parameter_code("")


def test_protocol_status_is_driven_by_priority_and_missing_stage() -> None:
    assert (
        contest_protocol_status(FindingStatus.CANDIDATE, review_priority=ReviewPriority.HIGH)
        is ContestProtocolStatus.CRITICAL
    )
    assert (
        contest_protocol_status(FindingStatus.CANDIDATE, review_priority=ReviewPriority.MEDIUM)
        is ContestProtocolStatus.WARNING
    )
    assert contest_protocol_status(FindingStatus.CANDIDATE) is ContestProtocolStatus.WARNING
    assert (
        contest_protocol_status(FindingStatus.MISSING_EVIDENCE, missing_stage=DocStage.ID)
        is ContestProtocolStatus.ID_MISSING
    )
    assert (
        contest_protocol_status(FindingStatus.MISSING_EVIDENCE)
        is ContestProtocolStatus.COMPARISON_IMPOSSIBLE
    )
    assert (
        contest_protocol_status(FindingStatus.AUTO_NO_DIFFERENCE) is ContestProtocolStatus.OK
    )
    assert (
        contest_protocol_status(FindingStatus.LOW_QUALITY)
        is ContestProtocolStatus.COMPARISON_IMPOSSIBLE
    )


def test_submission_payload_validates_against_organizer_schema() -> None:
    schema = json.loads(SUBMISSION_SCHEMA.read_text(encoding="utf-8"))
    group = _group(
        _fragment(EvidenceRole.EXPECTED, DocStage.PD, value="12.5"),
        _fragment(EvidenceRole.ACTUAL, DocStage.RD, value="11.0", page=3),
    )
    violation = build_check(_finding(), group, criticality="HIGH")
    missing = build_check(
        _finding(FindingStatus.MISSING_EVIDENCE, rule_code="pz-1", group_id=None),
        missing_stage=DocStage.ID,
    )
    abstained = build_check(
        _finding(FindingStatus.ABSTAIN, rule_code="KR-55", group_id=None),
        location="РД, 12345-КР, стр. 1",
    )

    payload = build_submission("obj-1", [violation, missing, abstained])
    jsonschema.Draft202012Validator(schema).validate(payload)

    checks = payload["checks"]
    assert isinstance(checks, list)
    assert [item["parameter_code"] for item in checks] == ["AR-014", "KR-055", "PZ-001"]
    assert checks[0]["violation_label"] == "VIOLATION_PRESENT"
    assert checks[0]["protocol_status"] == "CRITICAL"
    assert checks[0]["pd_value"] == "12.5"
    assert checks[0]["rd_value"] == "11.0"
    assert checks[0]["location"] == "RD, 12345-RD, рев. 2, лист 7, стр. 3"
    assert checks[0]["evidence"] == [
        {"stage": "PD", "file_id": "file-pd", "pdf_page_number": 7},
        {"stage": "RD", "file_id": "file-rd", "pdf_page_number": 3},
    ]
    assert checks[2]["protocol_status"] == "ID_MISSING"
    assert checks[2]["evidence"] == []


def test_violation_without_evidence_never_reaches_the_answer() -> None:
    """Домен уже требует evidence_group_id; здесь ловим несобранное доказательство."""

    with pytest.raises(ValueError, match="локализация"):
        build_check(_finding(), None)
    with pytest.raises(ValueError, match="локализация"):
        build_check(_finding(), _group())


def test_evidence_of_another_rule_cannot_be_attached() -> None:
    other = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD), rule_code="KR-055")
    with pytest.raises(ValueError, match="подставлено"):
        build_check(_finding(), other)


def test_evidence_group_id_mismatch_is_refused() -> None:
    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD), group_id="eg-other")
    with pytest.raises(ValueError, match="evidence_group_id"):
        build_check(_finding(), group)


def test_page_numbering_starts_at_one() -> None:
    with pytest.raises(ValueError, match="страницы"):
        _fragment(EvidenceRole.ACTUAL, DocStage.RD, page=0)


def test_candidate_on_ungrounded_value_is_refused() -> None:
    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD, grounded=False))
    with pytest.raises(ValueError, match="токенами источника"):
        build_check(_finding(), group)


def test_dual_read_requirement_is_enforced_when_asked() -> None:
    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD, second_read=None))
    build_check(_finding(), group)
    with pytest.raises(ValueError, match="двойного чтения"):
        build_check(_finding(), group, require_second_read=True)
    agreed = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD, second_read=True))
    assert build_check(_finding(), agreed, require_second_read=True).evidence


def test_dual_read_flag_on_the_rule_is_enough_without_a_caller_flag() -> None:
    """`dual_read_required` из матрицы не должен зависеть от памяти вызывающего."""

    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD, second_read=None))
    rule = {"extractor": {"dual_read_required": True}}
    with pytest.raises(ValueError, match="двойного чтения"):
        build_check(_finding(), group, rule=rule)
    agreed = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD, second_read=True))
    assert build_check(_finding(), agreed, rule=rule).evidence


def test_two_values_on_one_stage_are_a_linkage_error() -> None:
    group = _group(
        _fragment(EvidenceRole.ACTUAL, DocStage.RD, value="11.0"),
        EvidenceFragment(
            fragment_id="frag-context-rd",
            role=EvidenceRole.CONTEXT,
            document=DocumentRef(
                file_id="file-rd",
                file_hash="a" * 64,
                doc_stage=DocStage.RD,
                document_code="12345-RD",
                revision="2",
                approval_status=ApprovalStatus.APPROVED,
            ),
            page=4,
            polygon_source=SQUARE,
            polygon_norm=SQUARE,
            extracted=Extraction(
                raw_token="99.9",  # noqa: S106
                engine=ExtractionEngine.OCR,
                engine_version="rapidocr-1.3",
                confidence=0.4,
                normalized_value="99.9",
                grounded_in_source_tokens=True,
            ),
        ),
    )
    with pytest.raises(ValueError, match="связка не однозначна"):
        build_check(_finding(), group)


def test_code_outside_the_matrix_is_refused_loudly() -> None:
    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD))
    check = build_check(_finding(), group)
    assert build_submission("obj-1", [check], known_codes=["ar-14"])["checks"]
    with pytest.raises(ValueError, match="нет в матрице"):
        build_submission("obj-1", [check], known_codes=["PZ-001"])


def test_submission_is_deterministic_and_deduplicated() -> None:
    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD))
    check = build_check(_finding(), group)
    payload = build_submission("obj-1", [check, check])
    checks = payload["checks"]
    assert isinstance(checks, list)
    assert len(checks) == 1
    with pytest.raises(ValueError, match="object_id"):
        build_submission("  ", [check])


def test_findings_to_submission_is_the_only_assembly_path() -> None:
    group = _group(_fragment(EvidenceRole.ACTUAL, DocStage.RD, second_read=True))
    candidate = _finding()
    equal = _finding(FindingStatus.AUTO_NO_DIFFERENCE, rule_code="KR-055", group_id="eg-eq")
    equal_group = _group(
        _fragment(EvidenceRole.ACTUAL, DocStage.RD, second_read=True),
        rule_code="KR-055",
        group_id="eg-eq",
    )
    payload = findings_to_submission(
        "obj-1",
        [candidate, equal],
        [group, equal_group],
    )
    labels = [item["violation_label"] for item in payload["checks"]]
    assert "VIOLATION_PRESENT" in labels
    assert "NO_VIOLATION" in labels
    assert "AUTO_NO_DIFFERENCE" not in json.dumps(payload)
