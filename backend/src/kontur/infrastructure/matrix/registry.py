"""Файловый реестр правил. Реализация порта RuleRegistry (ADR-0004)."""

from __future__ import annotations

import json
from collections import Counter
from functools import cached_property
from pathlib import Path

from kontur.domain.rule_codes import canonicalize_rule_code

EXPECTED_PARAM_COUNT = 132
KNOWN_COVERAGE = frozenset(
    {
        "executable",
        "extractor_missing",
        "source_missing",
        "advisory",
        "not_applicable",
    }
)


def discover_matrix_root(start: Path | None = None) -> Path:
    """Ищет `data/matrix/rules` вверх от файла. Пустой каталог — ошибка, не 'empty'."""

    here = start or Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "data" / "matrix"
        if (candidate / "rules").is_dir():
            return candidate
    raise FileNotFoundError(
        "каталог data/matrix/rules не найден: образ собран без матрицы "
        "или рабочий каталог неверен"
    )


DEFAULT_ROOT = discover_matrix_root()


class FileRuleRegistry:
    """Читает `data/matrix/rules/*.json` и отдаёт правила как данные."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or DEFAULT_ROOT
        self._rules_dir = self._root / "rules"

    @cached_property
    def _rules(self) -> dict[str, dict[str, object]]:
        if not self._rules_dir.is_dir():
            raise FileNotFoundError(f"{self._rules_dir}: нет каталога правил")
        rules: dict[str, dict[str, object]] = {}
        for path in sorted(self._rules_dir.glob("*.json")):
            rule = json.loads(path.read_text(encoding="utf-8"))
            code = canonicalize_rule_code(str(rule["code"]))
            if code != str(rule["code"]):
                raise ValueError(f"{path.name}: код {rule['code']!r} не канонический {code!r}")
            coverage = str(rule.get("coverage"))
            if coverage not in KNOWN_COVERAGE:
                raise ValueError(f"{path.name}: неизвестный coverage {coverage!r}")
            if code in rules:
                raise ValueError(f"дубликат правила: {code}")
            rules[code] = rule
        if not rules:
            raise FileNotFoundError(f"{self._rules_dir}: матрица пуста, сравнение невозможно")
        return rules

    @property
    def matrix_version(self) -> str:
        versions = {str(rule["matrix_version"]) for rule in self._rules.values()}
        if len(versions) > 1:
            raise ValueError(f"смешаны версии матрицы: {sorted(versions)}")
        return versions.pop()

    def get(self, code: str) -> dict[str, object]:
        canonical = canonicalize_rule_code(code)
        try:
            return self._rules[canonical]
        except KeyError as exc:
            raise KeyError(code) from exc

    def all_codes(self) -> list[str]:
        return list(self._rules)

    def coverage_report(self) -> dict[str, int]:
        """Честная разбивка покрытия. Неизвестный ключ не попадает в отчёт."""

        counter = Counter(str(rule["coverage"]) for rule in self._rules.values())
        report = {name: int(counter.get(name, 0)) for name in sorted(KNOWN_COVERAGE)}
        report["declared"] = len(self._rules)
        report["expected_total"] = EXPECTED_PARAM_COUNT
        return report
