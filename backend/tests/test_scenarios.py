"""Gate F: сценарии загрузки и комплектность (ТЗ п. 9.2).

Инвариант: отсутствие стадии НИКОГДА не даёт CANDIDATE/CONFIRMED_VIOLATION.
Каждый из 6 сценариев покрыт. EmptyPackageError на пустом пакете.
"""

from __future__ import annotations

import pytest

from kontur.application.scenarios import (
    CompletenessMap,
    detect_scenario,
    status_for_missing_stage,
)
from kontur.domain.models import DocStage
from kontur.domain.status_map import EmptyPackageError
from kontur.domain.statuses import Completeness, FindingStatus, Scenario

# ---------------------------------------------------------------------------
# detect_scenario
# ---------------------------------------------------------------------------


def _m(**kwargs: Completeness) -> CompletenessMap:
    """Краткий конструктор CompletenessMap; не указанные стадии = MISSING."""
    base: CompletenessMap = {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    for k, v in kwargs.items():
        base[DocStage[k]] = v
    return base


class TestDetectScenario:
    def test_full(self) -> None:
        m = _m(PD=Completeness.UPLOADED, RD=Completeness.UPLOADED, ID=Completeness.UPLOADED)
        assert detect_scenario(m) is Scenario.FULL

    def test_pd_rd_only(self) -> None:
        m = _m(PD=Completeness.UPLOADED, RD=Completeness.UPLOADED)
        assert detect_scenario(m) is Scenario.PD_RD_ONLY

    def test_pd_id_only(self) -> None:
        m = _m(PD=Completeness.UPLOADED, ID=Completeness.UPLOADED)
        assert detect_scenario(m) is Scenario.PD_ID_ONLY

    def test_rd_id_only(self) -> None:
        m = _m(RD=Completeness.UPLOADED, ID=Completeness.UPLOADED)
        assert detect_scenario(m) is Scenario.RD_ID_ONLY

    def test_single_pd(self) -> None:
        assert detect_scenario(_m(PD=Completeness.UPLOADED)) is Scenario.SINGLE_ONLY

    def test_single_rd(self) -> None:
        assert detect_scenario(_m(RD=Completeness.UPLOADED)) is Scenario.SINGLE_ONLY

    def test_single_id(self) -> None:
        assert detect_scenario(_m(ID=Completeness.UPLOADED)) is Scenario.SINGLE_ONLY

    def test_partially_loaded_beats_full_set(self) -> None:
        """PARTIAL на любой стадии → PARTIALLY_LOADED, даже если остальные UPLOADED."""
        m = _m(PD=Completeness.PARTIAL, RD=Completeness.UPLOADED, ID=Completeness.UPLOADED)
        assert detect_scenario(m) is Scenario.PARTIALLY_LOADED

    def test_partially_loaded_single(self) -> None:
        assert detect_scenario(_m(PD=Completeness.PARTIAL)) is Scenario.PARTIALLY_LOADED

    def test_empty_raises(self) -> None:
        with pytest.raises(EmptyPackageError):
            detect_scenario(_m())

    def test_all_missing_raises(self) -> None:
        m: CompletenessMap = {
            DocStage.PD: Completeness.MISSING,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        }
        with pytest.raises(EmptyPackageError):
            detect_scenario(m)


# ---------------------------------------------------------------------------
# status_for_missing_stage — инвариант: не CANDIDATE, не CONFIRMED_VIOLATION
# ---------------------------------------------------------------------------


class TestStatusForMissingStage:
    def test_not_applicable_when_not_required_and_not_applicable(self) -> None:
        status = status_for_missing_stage(
            stage_required_by_rule=False,
            stage_applicable_to_object=False,
        )
        assert status is FindingStatus.NOT_APPLICABLE

    def test_not_applicable_when_not_required_but_applicable(self) -> None:
        """Стадия применима к объекту, но правило её не требует → NOT_APPLICABLE."""
        status = status_for_missing_stage(
            stage_required_by_rule=False,
            stage_applicable_to_object=True,
        )
        assert status is FindingStatus.NOT_APPLICABLE

    def test_missing_evidence_when_required_but_stage_absent(self) -> None:
        status = status_for_missing_stage(
            stage_required_by_rule=True,
            stage_applicable_to_object=True,
        )
        assert status is FindingStatus.MISSING_EVIDENCE

    def test_not_applicable_overrides_required_when_not_applicable_to_object(self) -> None:
        """Даже если правило требует стадию, но она неприменима к объекту — NOT_APPLICABLE."""
        status = status_for_missing_stage(
            stage_required_by_rule=True,
            stage_applicable_to_object=False,
        )
        assert status is FindingStatus.NOT_APPLICABLE

    @pytest.mark.parametrize(
        "required,applicable",
        [
            (False, False),
            (False, True),
            (True, True),
            (True, False),
        ],
    )
    def test_never_returns_candidate_or_violation(
        self, required: bool, applicable: bool
    ) -> None:
        """Инвариант ТЗ п. 9.2: отсутствие документа — не нарушение."""
        status = status_for_missing_stage(
            stage_required_by_rule=required,
            stage_applicable_to_object=applicable,
        )
        assert status not in (
            FindingStatus.CANDIDATE,
            FindingStatus.CONFIRMED_VIOLATION,
        ), f"Неожиданный статус {status} для required={required}, applicable={applicable}"
