"""Репетиция холодного демо. Не Polar, не TEST_HIDDEN, не закрытие гейтов I/J/K."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kontur.domain.models import Finding
from kontur.domain.statuses import FindingStatus
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT

DEMO_OBJECT_ID = "OBJ-DEMO-COLD-START"
DEMO_CODES: tuple[str, ...] = ("PZ-001", "KR-055", "AR-041")
COMPOSE_DEMO_SERVICES: tuple[str, ...] = (
    "postgres",
    "redis",
    "rabbitmq",
    "minio",
    "core",
    "outbox-relay",
    "inbox-consumer",
    "gateway",
)
# Ведро покрытия — не только executable/extractor_missing: правило может быть
# advisory (компаратор не даёт CANDIDATE), source_missing (нет источника в ТЗ)
# или not_applicable. Разбивка обязана сходиться к 132 по всем вёдрам.
COVERAGE_BUCKETS: tuple[str, ...] = (
    "executable",
    "extractor_missing",
    "advisory",
    "source_missing",
    "not_applicable",
)
HONEST_EXECUTABLE_MIN = 20
CLOSES_GATE_K = False
CLOSES_GATE_J = False


def demo_findings(findings: Sequence[Finding]) -> dict[str, Finding]:
    by_code = {item.rule_code: item for item in findings}
    missing = [code for code in DEMO_CODES if code not in by_code]
    if missing:
        raise KeyError(f"в отчёте нет правил демо: {missing}")
    return {code: by_code[code] for code in DEMO_CODES}


def candidate_codes(findings: Sequence[Finding]) -> tuple[str, ...]:
    return tuple(
        item.rule_code
        for item in findings
        if item.finding_status is FindingStatus.CANDIDATE
    )


def assert_honest_coverage(report: Mapping[str, int]) -> None:
    """Разбивка coverage, не заявление, что вся матрица executable."""

    declared = int(report.get("declared", -1))
    expected = int(report.get("expected_total", -1))
    if expected != EXPECTED_PARAM_COUNT or declared != EXPECTED_PARAM_COUNT:
        raise AssertionError(f"матрица {declared}/{expected}, ожидалось {EXPECTED_PARAM_COUNT}")
    buckets = {name: int(report.get(name, 0)) for name in COVERAGE_BUCKETS}
    executable = buckets["executable"]
    if executable < HONEST_EXECUTABLE_MIN:
        raise AssertionError(
            f"executable={executable}, ожидалось не меньше {HONEST_EXECUTABLE_MIN}"
        )
    if executable >= EXPECTED_PARAM_COUNT:
        raise AssertionError("нельзя заявить всю матрицу executable")
    if buckets["extractor_missing"] <= 0:
        raise AssertionError("extractor_missing=0: незакрытые извлечения обязаны быть видны")
    if sum(buckets.values()) != EXPECTED_PARAM_COUNT:
        raise AssertionError("разбивка coverage не сходится к 132")
