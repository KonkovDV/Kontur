"""Dry-run 132 правил: скомпилированная матрица, без документов, без человеческих вердиктов."""

from __future__ import annotations

from pathlib import Path

from kontur.application.dry_run import CI_DRY_RUN_SECONDS, TZ_DRY_RUN_SECONDS, dry_run_matrix
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, FindingStatus
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]


def test_dry_run_walks_compiled_132_rules_under_budget() -> None:
    registry = FileRuleRegistry(REPO / "data" / "matrix")
    report = dry_run_matrix(registry)
    assert report.declared == EXPECTED_PARAM_COUNT
    assert report.elapsed_seconds < CI_DRY_RUN_SECONDS
    assert report.elapsed_seconds < TZ_DRY_RUN_SECONDS
    assert report.human_verdicts == 0
    assert not report.coverage_mismatch
    statuses = {FindingStatus(name) for name in report.by_status}
    assert statuses.isdisjoint(HUMAN_ONLY_STATUSES)
    assert sum(report.by_coverage.values()) == EXPECTED_PARAM_COUNT
    assert report.by_coverage.get("executable", 0) == registry.coverage_report()["executable"]
