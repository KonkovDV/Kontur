"""Проекция внутренних статусов на буквальные имена ТЗ (Gate B)."""

from __future__ import annotations

import pytest

from kontur.application.pipeline import Stage, halt_status
from kontur.application.scenarios import detect_scenario
from kontur.domain.models import DocStage, Finding
from kontur.domain.status_map import (
    EmptyPackageError,
    on_the_wire,
    protocol_status,
    tz_upload_status,
)
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState, ReviewPriority


def test_upload_status_uses_tz_prefix() -> None:
    assert tz_upload_status(DocStage.PD, Completeness.UPLOADED) == "PD_UPLOADED"
    assert tz_upload_status(DocStage.RD, Completeness.PARTIAL) == "RD_PARTIAL"
    assert tz_upload_status(DocStage.ID, Completeness.MISSING) == "ID_MISSING"


def test_process_projects_to_protocol_vocabulary() -> None:
    assert protocol_status(ProcessState.COMPLETED) == "VERIFICATION_COMPLETED"
    assert protocol_status(ProcessState.FINALIZED) == "PROTOCOL_FINALIZED"
    assert protocol_status(ProcessState.PENDING) is None


def test_auto_no_difference_stays_off_the_wire() -> None:
    assert not on_the_wire(FindingStatus.AUTO_NO_DIFFERENCE)
    assert on_the_wire(FindingStatus.CANDIDATE)


def test_empty_package_is_not_a_scenario() -> None:
    mapping = {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    with pytest.raises(EmptyPackageError):
        detect_scenario(mapping)


def test_intake_failure_is_not_a_finding() -> None:
    with pytest.raises(ValueError, match="RejectionReason"):
        halt_status(Stage.L0_INTAKE)


def test_matrix_engine_failure_is_clarification() -> None:
    assert halt_status(Stage.L6_MATRIX) is FindingStatus.CLARIFICATION_REQUIRED


def test_candidate_without_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="evidence_group_id"):
        Finding(
            finding_id="f-1",
            rule_code="AR-41",
            finding_status=FindingStatus.CANDIDATE,
            review_priority=ReviewPriority.HIGH,
            matrix_version="draft-0",
            rule_version="0.1.0",
            model_version="none",
        )


def test_missing_evidence_may_omit_evidence_group() -> None:
    finding = Finding(
        finding_id="f-2",
        rule_code="AR-41",
        finding_status=FindingStatus.MISSING_EVIDENCE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
    )
    assert finding.evidence_group_id is None
