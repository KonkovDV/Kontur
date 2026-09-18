"""Сценарии загрузки: отсутствие стадии никогда не создаёт нарушение (Gate F)."""

from __future__ import annotations

import pytest

from kontur.application.scenarios import detect_scenario, status_for_missing_stage
from kontur.domain.models import DocStage
from kontur.domain.status_map import EmptyPackageError
from kontur.domain.statuses import Completeness, FindingStatus, Scenario

FULL_MAP = {
    DocStage.PD: Completeness.UPLOADED,
    DocStage.RD: Completeness.UPLOADED,
    DocStage.ID: Completeness.UPLOADED,
}


def test_empty_package_is_not_a_scenario() -> None:
    mapping = {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    with pytest.raises(EmptyPackageError):
        detect_scenario(mapping)


def test_full_scenario() -> None:
    assert detect_scenario(FULL_MAP) is Scenario.FULL


def test_missing_id_gives_pd_rd_only() -> None:
    mapping = FULL_MAP | {DocStage.ID: Completeness.MISSING}
    assert detect_scenario(mapping) is Scenario.PD_RD_ONLY


def test_partial_wins_over_full() -> None:
    mapping = FULL_MAP | {DocStage.ID: Completeness.PARTIAL}
    assert detect_scenario(mapping) is Scenario.PARTIALLY_LOADED


def test_single_stage() -> None:
    mapping = {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    assert detect_scenario(mapping) is Scenario.SINGLE_ONLY


def test_missing_rd_gives_pd_id_only() -> None:
    mapping = FULL_MAP | {DocStage.RD: Completeness.MISSING}
    assert detect_scenario(mapping) is Scenario.PD_ID_ONLY


def test_missing_pd_gives_rd_id_only() -> None:
    mapping = FULL_MAP | {DocStage.PD: Completeness.MISSING}
    assert detect_scenario(mapping) is Scenario.RD_ID_ONLY


def test_single_rd_is_single_only() -> None:
    mapping = {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }
    assert detect_scenario(mapping) is Scenario.SINGLE_ONLY


def test_single_id_is_single_only() -> None:
    mapping = {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.UPLOADED,
    }
    assert detect_scenario(mapping) is Scenario.SINGLE_ONLY


def test_missing_required_stage_is_missing_evidence() -> None:
    status = status_for_missing_stage(stage_required_by_rule=True, stage_applicable_to_object=True)
    assert status is FindingStatus.MISSING_EVIDENCE


def test_inapplicable_stage_is_not_applicable() -> None:
    status = status_for_missing_stage(stage_required_by_rule=True, stage_applicable_to_object=False)
    assert status is FindingStatus.NOT_APPLICABLE


def test_missing_stage_never_returns_violation() -> None:
    for required in (True, False):
        for applicable in (True, False):
            status = status_for_missing_stage(
                stage_required_by_rule=required,
                stage_applicable_to_object=applicable,
            )
            assert status not in {FindingStatus.CANDIDATE, FindingStatus.CONFIRMED_VIOLATION}
