"""Сценарий загрузки и комплектность (ТЗ п. 9.2).

Инвариант: комплектность описывает входные данные и никогда не превращается
в нарушение. Отсутствие стадии даёт NOT_APPLICABLE либо MISSING_EVIDENCE.
"""

from __future__ import annotations

from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness, FindingStatus, Scenario

CompletenessMap = dict[DocStage, Completeness]


def detect_scenario(completeness: CompletenessMap) -> Scenario:
    present = {
        stage
        for stage, state in completeness.items()
        if state is not Completeness.MISSING
    }
    partial = any(state is Completeness.PARTIAL for state in completeness.values())

    if partial:
        return Scenario.PARTIALLY_LOADED
    if present == {DocStage.PD, DocStage.RD, DocStage.ID}:
        return Scenario.FULL
    if present == {DocStage.PD, DocStage.RD}:
        return Scenario.PD_RD_ONLY
    if present == {DocStage.PD, DocStage.ID}:
        return Scenario.PD_ID_ONLY
    if present == {DocStage.RD, DocStage.ID}:
        return Scenario.RD_ID_ONLY
    return Scenario.SINGLE_ONLY


def status_for_missing_stage(
    *,
    stage_required_by_rule: bool,
    stage_applicable_to_object: bool,
) -> FindingStatus:
    """Чем закрывается правило, которому не хватает стадии.

    Никогда не возвращает CANDIDATE или CONFIRMED_VIOLATION: отсутствие
    документа не является расхождением по существу.
    """

    if not stage_applicable_to_object:
        return FindingStatus.NOT_APPLICABLE
    if stage_required_by_rule:
        return FindingStatus.MISSING_EVIDENCE
    return FindingStatus.NOT_APPLICABLE
