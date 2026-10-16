"""Репетиция холодного демо. Не Polar, не TEST_HIDDEN, не закрытие гейтов I/J/K."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

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


DEFAULT_HEALTHZ_URL = "http://127.0.0.1:8000/api/v1/healthz"
_INSECURE_ENVS = frozenset({"dev", "demo"})


def preflight(
    env: Mapping[str, str],
    *,
    font: Path | None,
    healthz: Callable[[], str | None] | None,
) -> list[str]:
    """Проверки до показа: флаг legacy-токенов, шрифт, /healthz. Пусто — можно начинать.

    `healthz` возвращает None при ответе 200 `{"status":"ok"}` или текст ошибки;
    None вместо функции — проверка ядра пропущена (офлайн-прогон).
    """

    problems: list[str] = []
    flag = (env.get("KONTUR_ALLOW_INSECURE_DEV_AUTH") or "").strip().lower() == "true"
    kontur_env = (env.get("KONTUR_ENV") or "").strip().lower()
    if flag and kontur_env not in _INSECURE_ENVS:
        shown = f"при KONTUR_ENV={kontur_env}" if kontur_env else "без KONTUR_ENV"
        problems.append(
            f"флаг: KONTUR_ALLOW_INSECURE_DEV_AUTH=true {shown} — ядро не стартует. "
            "Для демо задайте KONTUR_ENV=demo, для pilot/prod уберите флаг"
        )
    elif not flag:
        problems.append(
            "флаг: KONTUR_ALLOW_INSECURE_DEV_AUTH не задан — учебные токены демо ядро "
            "не примет. Для репетиции: KONTUR_ALLOW_INSECURE_DEV_AUTH=true и KONTUR_ENV=demo"
        )
    if font is None or not font.is_file():
        problems.append(
            "шрифт: нет TTF с кириллицей — POST /demo/kit ответит 503. "
            "Нужен vendor/fonts/NotoSans-Regular.ttf или KONTUR_TEST_FONT=<путь к .ttf>"
        )
    if healthz is not None:
        error = healthz()
        if error is not None:
            problems.append(
                f"ядро: {error}. Поднимите compose (docs/DEMO_COLD_START.md) и повторите"
            )
    return problems
