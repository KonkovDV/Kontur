"""Гейт честности формулировок.

Пороги ТЗ — минимумы приёмки. Пока метрика не измерена на frozen validation с
указанием размера выборки и интервала, репозиторий не публикует ни числа, ни
утверждения о готовности. Скрипт ищет запрещённые формулировки в публичных
файлах и падает с ненулевым кодом.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_GLOBS = ("README.md", "AGENTS.md", "docs/**/*.md", "web/**/*.md", "data/**/*.md")

FORBIDDEN: tuple[tuple[str, str], ...] = (
    (r"полностью автоматическ\w*\s+надзор", "автономный надзор не заявляется"),
    (r"(?<!не )замен\w+\s+инспектора", "система не заменяет инспектора"),
    (r"132\s+(?:проверк|параметр)\w*\s+реализован", "покрытие публикуется в разбивке coverage"),
    (r"интеграция\s+с\s+ИАИС[^.]{0,40}готова", "интеграция без sandbox-контракта не готова"),
    (r"production[- ]ready", "скелет не production-ready"),
    (r"\bSLA\b\s*99", "SLA не подтверждается локальным демо"),
    (r"поддерживаем\s+DWG", "DWG = NOT_SUPPORTED до ответа организатора"),
)

# Числа-метрики допустимы только рядом с явной оговоркой о статусе замера.
METRIC_PATTERN = re.compile(
    r"\b(?:точность|precision|recall|f1|accuracy)\b[^.\n]{0,40}?[0-9]{2,3}\s?%",
    re.IGNORECASE,
)
ALLOWED_NEAR_METRIC = ("порог", "минимум", "цель", "не измерен", "приёмк")

# Текст между маркерами не сканируется: так описывается сам список запретов.
ALLOW_BLOCK = re.compile(
    r"<!--\s*claims-lint:\s*allow\s*-->.*?<!--\s*/claims-lint\s*-->",
    re.DOTALL,
)


def public_files() -> list[Path]:
    files: list[Path] = []
    for pattern in PUBLIC_GLOBS:
        files.extend(ROOT.glob(pattern))
    return [path for path in files if path.is_file()]


def main() -> int:
    problems: list[str] = []
    for path in public_files():
        text = ALLOW_BLOCK.sub("", path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        for pattern, message in FORBIDDEN:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                problems.append(f"{rel}: «{match.group(0)}» — {message}")
        for match in METRIC_PATTERN.finditer(text):
            window = text[max(0, match.start() - 160) : match.end() + 160].lower()
            if not any(token in window for token in ALLOWED_NEAR_METRIC):
                problems.append(
                    f"{rel}: «{match.group(0)}» — число без пометки о статусе замера"
                )

    for problem in problems:
        print(problem)
    if problems:
        print(f"\nclaims: {len(problems)} нарушени(й)")
        return 1
    print(f"claims: чисто, проверено файлов: {len(public_files())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
