"""Package completeness scenarios (Gate F).

Сценарии определяют, какие стадии пакета документов присутствуют, и решают,
какие правила применимы. Ключевые инварианты:

  1. ОТСУТСТВИЕ стадии через весь пакет ≠ нарушение (результат MISSING_EVIDENCE / NOT_APPLICABLE).
  2. Пустой пакет без документов (ни PD, ни RD, ни ID) — ошибка (EmptyPackageError).
  3. Сценарий FULL запускает все исполняемые правила.

Refs: ТЗ §8.2-8.4, Gate F, PLAN_2026_09, RED_TEAM (RT-2609-21).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, Set


class Stage(str, Enum):
    PD = "PD"  # Проектная документация
    RD = "RD"  # Рабочая документация
    ID = "ID"  # Исполнительная документация (ход строительства)


ALL_STAGES: FrozenSet[Stage] = frozenset(Stage)


class PackageScenario(str, Enum):
    """Scenario identifier for a given document package."""

    FULL = "FULL"  # PD + RD + ID присутствуют
    PD_RD_ONLY = "PD_RD_ONLY"  # Предварительный проект / начало стройтельства
    PD_ONLY = "PD_ONLY"  # Только проект; редко, но допустимо (ЕкСп) 
    RD_ONLY = "RD_ONLY"  # Только РД (доминирующий практика реконструкции)
    ID_ONLY = "ID_ONLY"  # Исполнительная докум. без PD/RD (устаревший объект)
    PARTIALLY_LOADED = "PARTIALLY_LOADED"  # Некоторые листы PDF повреждены/отсутствуют
    EMPTY_PACKAGE = "EMPTY_PACKAGE"  # Ни одного документа не загружено


class EmptyPackageError(ValueError):
    """Raised when the submitted package contains no usable documents at all."""


@dataclass(frozen=True)
class ScenarioResult:
    """Resolved scenario plus the stages that are actually available."""

    scenario: PackageScenario
    available_stages: FrozenSet[Stage]
    #: Stages present but with partially-loaded/corrupt documents
    degraded_stages: FrozenSet[Stage] = field(default_factory=frozenset)

    @property
    def has_pd(self) -> bool:
        return Stage.PD in self.available_stages

    @property
    def has_rd(self) -> bool:
        return Stage.RD in self.available_stages

    @property
    def has_id(self) -> bool:
        return Stage.ID in self.available_stages


def resolve_scenario(
    present_stages: Set[Stage] | FrozenSet[Stage],
    degraded_stages: Set[Stage] | FrozenSet[Stage] | None = None,
) -> ScenarioResult:
    """Derive the PackageScenario from the set of present stages.

    Args:
        present_stages: Stages for which at least one document was loaded.
        degraded_stages: Stages present but with quality issues
            (partial OCR, corrupt pages). These stages are included in
            `available_stages` but flagged as degraded.

    Returns:
        ScenarioResult with the resolved scenario.

    Raises:
        EmptyPackageError: If present_stages is empty and no degraded stages.
            This is an error condition -- the caller must not proceed.

    """
    present = frozenset(present_stages)
    degraded = frozenset(degraded_stages or set())
    all_present = present | degraded

    if not all_present:
        raise EmptyPackageError(
            "Package contains no usable documents. Cannot evaluate. "
            "Verify document upload and extraction pipeline."
        )

    if Stage.PD in all_present and Stage.RD in all_present and Stage.ID in all_present:
        if degraded:
            scenario = PackageScenario.PARTIALLY_LOADED
        else:
            scenario = PackageScenario.FULL
    elif Stage.PD in all_present and Stage.RD in all_present:
        scenario = PackageScenario.PD_RD_ONLY
    elif Stage.PD in all_present and Stage.RD not in all_present:
        scenario = PackageScenario.PD_ONLY
    elif Stage.RD in all_present and Stage.PD not in all_present:
        scenario = PackageScenario.RD_ONLY
    elif Stage.ID in all_present and Stage.PD not in all_present and Stage.RD not in all_present:
        scenario = PackageScenario.ID_ONLY
    else:
        scenario = PackageScenario.PARTIALLY_LOADED

    return ScenarioResult(
        scenario=scenario,
        available_stages=all_present,
        degraded_stages=degraded,
    )


def stage_required_for_rule(
    required_stages: FrozenSet[Stage],
    scenario: ScenarioResult,
) -> bool:
    """Return True if all stages required by a rule are available in this scenario.

    INVARIANT: missing stage ≠ violation.
    If a required stage is absent, the rule yields MISSING_EVIDENCE or NOT_APPLICABLE,
    NOT CANDIDATE. This function must be consulted before running any comparator.

    Args:
        required_stages: Stages the rule needs (from matrix `stages_required`).
        scenario: Resolved scenario for the package.

    Returns:
        True if all required stages are present and can be used.
    """
    return required_stages.issubset(scenario.available_stages)
