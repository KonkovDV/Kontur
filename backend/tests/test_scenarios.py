"""Tests for package completeness scenarios (Gate F).

Key invariants:
  - Missing stage ≠ violation (rule yields MISSING_EVIDENCE or NOT_APPLICABLE)
  - Empty package → EmptyPackageError
  - FULL only when all 3 stages healthy
  - PARTIALLY_LOADED when any degraded stage present

Refs: ТЗ §8.2-8.4, Gate F (20.09), PLAN_2026_09.
"""
from __future__ import annotations

import pytest

from kontur.application.scenarios import (
    EmptyPackageError,
    PackageScenario,
    Stage,
    resolve_scenario,
    stage_required_for_rule,
)


def test_full_scenario_all_three_stages() -> None:
    result = resolve_scenario({Stage.PD, Stage.RD, Stage.ID})
    assert result.scenario == PackageScenario.FULL
    assert result.has_pd and result.has_rd and result.has_id


def test_pd_rd_only_scenario() -> None:
    result = resolve_scenario({Stage.PD, Stage.RD})
    assert result.scenario == PackageScenario.PD_RD_ONLY
    assert result.has_pd and result.has_rd
    assert not result.has_id


def test_rd_only_scenario() -> None:
    result = resolve_scenario({Stage.RD})
    assert result.scenario == PackageScenario.RD_ONLY
    assert result.has_rd
    assert not result.has_pd


def test_pd_only_scenario() -> None:
    result = resolve_scenario({Stage.PD})
    assert result.scenario == PackageScenario.PD_ONLY
    assert result.has_pd
    assert not result.has_rd


def test_id_only_scenario() -> None:
    result = resolve_scenario({Stage.ID})
    assert result.scenario == PackageScenario.ID_ONLY
    assert result.has_id
    assert not result.has_pd and not result.has_rd


def test_partially_loaded_when_all_stages_but_some_degraded() -> None:
    """All 3 stages present but ID is degraded → PARTIALLY_LOADED (not FULL)."""
    result = resolve_scenario(
        present_stages={Stage.PD, Stage.RD},
        degraded_stages={Stage.ID},
    )
    assert result.scenario == PackageScenario.PARTIALLY_LOADED
    assert Stage.ID in result.degraded_stages


def test_empty_package_raises_error() -> None:
    """Empty package MUST raise — caller cannot silently proceed."""
    with pytest.raises(EmptyPackageError):
        resolve_scenario(set())


def test_missing_stage_does_not_satisfy_rule_requirement() -> None:
    """Ключевой инвариант: отсутствие стадии ≠ нарушение.

    Если правило IOS4-078 требует [PD, RD], а RD отсутствует —
    результат MISSING_EVIDENCE, не CANDIDATE.
    """
    from collections.abc import Set
    from typing import FrozenSet

    pd_only_scenario = resolve_scenario({Stage.PD})
    ios4_078_required = frozenset({Stage.PD, Stage.RD})

    satisfied = stage_required_for_rule(ios4_078_required, pd_only_scenario)
    assert satisfied is False, (
        "stage_required_for_rule must return False when a required stage is absent. "
        "Missing stage ≠ violation (invariant ™1)"
    )
