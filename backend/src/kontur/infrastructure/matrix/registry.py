"""Файловый реестр правил. Реализация порта RuleRegistry (ADR-0004)."""

from __future__ import annotations

import json
from collections import Counter
from functools import cached_property
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[5] / "data" / "matrix"
EXPECTED_PARAM_COUNT = 132


class FileRuleRegistry:
    """Читает `data/matrix/rules/*.json` и отдаёт правила как данные."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or DEFAULT_ROOT
        self._rules_dir = self._root / "rules"

    @cached_property
    def _rules(self) -> dict[str, dict[str, object]]:
        rules: dict[str, dict[str, object]] = {}
        for path in sorted(self._rules_dir.glob("*.json")):
            rule = json.loads(path.read_text(encoding="utf-8"))
            code = str(rule["code"])
            if code in rules:
                raise ValueError(f"дубликат правила: {code}")
            rules[code] = rule
        return rules

    @property
    def matrix_version(self) -> str:
        versions = {str(rule["matrix_version"]) for rule in self._rules.values()}
        if len(versions) > 1:
            raise ValueError(f"смешаны версии матрицы: {sorted(versions)}")
        return versions.pop() if versions else "empty"

    def get(self, code: str) -> dict[str, object]:
        return self._rules[code]

    def all_codes(self) -> list[str]:
        return list(self._rules)

    def coverage_report(self) -> dict[str, int]:
        """Честная разбивка покрытия. `declared` — сколько строк матрицы описано."""

        counter = Counter(str(rule["coverage"]) for rule in self._rules.values())
        report = {
            "executable": 0,
            "extractor_missing": 0,
            "source_missing": 0,
            "advisory": 0,
            "not_applicable": 0,
        }
        report.update(counter)
        report["declared"] = len(self._rules)
        report["expected_total"] = EXPECTED_PARAM_COUNT
        return report
