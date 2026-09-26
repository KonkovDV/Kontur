"""Dry-run 132 параметров по скомпилированной матрице.

Источник — `data/matrix/rules/`, не overrides и не сырой `rules` без compile.
Документов нет: каждое правило проходит evaluate_rule на пустой комплектности.
Это прогон движка, не «132 проверки реализованы» и не замер recall.
Бюджет гейта K — 30 минут; CI ловит зависание гораздо раньше.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from time import perf_counter

from kontur.application.evaluate import evaluate_rule
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry

TZ_DRY_RUN_SECONDS = 30 * 60
CI_DRY_RUN_SECONDS = 60

#: Семейства, которые слайс умеет исполнять: executable с другим типом — рассинхрон
#: между заявленным покрытием и кодом движка.
EXECUTABLE_EXTRACTOR_TYPES: frozenset[str] = frozenset(
    {
        "number",
        "geometry",
        "contour_area",
        "element_table",
        "enum",
        "text_regex",
        "exact_field",
        "presence",
    }
)


def _empty_completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


@dataclass(frozen=True, slots=True)
class DryRunReport:
    declared: int
    elapsed_seconds: float
    by_coverage: dict[str, int]
    by_status: dict[str, int]
    human_verdicts: int
    coverage_mismatch: tuple[str, ...]


def dry_run_matrix(registry: FileRuleRegistry | None = None) -> DryRunReport:
    """Прогнать все правила матрицы без документов и без человеческих вердиктов."""

    source = registry or FileRuleRegistry()
    completeness = _empty_completeness()
    coverage_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    human = 0
    mismatches: list[str] = []
    started = perf_counter()
    codes = source.all_codes()
    if len(codes) != EXPECTED_PARAM_COUNT:
        raise ValueError(
            f"матрица {len(codes)} правил, ожидалось {EXPECTED_PARAM_COUNT}"
        )
    for code in codes:
        rule = source.get(code)
        coverage = str(rule.get("coverage"))
        coverage_counts[coverage] += 1
        result = evaluate_rule(
            rule,
            object_id="dry-run",
            pages={},
            completeness=completeness,
        )
        status = result.finding.finding_status
        if status in HUMAN_ONLY_STATUSES:
            human += 1
            mismatches.append(f"{code}:{status.value}")
            continue
        status_counts[status.value] += 1
        if coverage == "executable" and status is FindingStatus.CLARIFICATION_REQUIRED:
            extractor = rule.get("extractor")
            extractor_type = extractor.get("type") if isinstance(extractor, dict) else None
            if extractor_type not in EXECUTABLE_EXTRACTOR_TYPES:
                mismatches.append(f"{code}:executable без экстрактора {extractor_type!r}")
    elapsed = perf_counter() - started
    return DryRunReport(
        declared=len(codes),
        elapsed_seconds=elapsed,
        by_coverage=dict(coverage_counts),
        by_status=dict(status_counts),
        human_verdicts=human,
        coverage_mismatch=tuple(mismatches),
    )
