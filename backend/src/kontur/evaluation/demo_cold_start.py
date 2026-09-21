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
HONEST_EXECUTABLE = 29
HONEST_EXTRACTOR_MISSING = 103
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
    executable = int(report.get("executable", -1))
    missing = int(report.get("extractor_missing", -1))
    if expected != EXPECTED_PARAM_COUNT or declared != EXPECTED_PARAM_COUNT:
        raise AssertionError(f"матрица {declared}/{expected}, ожидалось {EXPECTED_PARAM_COUNT}")
    if executable != HONEST_EXECUTABLE:
        raise AssertionError(f"executable={executable}, ожидалось {HONEST_EXECUTABLE}")
    if missing != HONEST_EXTRACTOR_MISSING:
        raise AssertionError(f"extractor_missing={missing}, ожидалось {HONEST_EXTRACTOR_MISSING}")
    if executable + missing != EXPECTED_PARAM_COUNT:
        raise AssertionError("разбивка coverage не сходится к 132")
