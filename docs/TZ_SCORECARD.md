# Три контура готовности (не приёмка ТЗ)

Машиночитаемый файл: [`data/dataset/tz_scorecard.json`](../data/dataset/tz_scorecard.json).
Пересборка: `python scripts/export_agent_dumps.py`.

Это **инженерный чеклист**, не Character Accuracy / Precision / Recall и не
заявление, что порог раздела 14 измерен. Гейты I/J/K/L в scorecard всегда
`false`. Поля «процентов готовности по ТЗ» нет.

## Зачем три контура

Одна цифра смешивает schema-valid правила, замер на GOLD и эксплуатацию.
ТЗ так принимать нельзя.

| Контур | Смысл | Сейчас |
|---|---|---|
| Code | Функции и автотесты | часть HTTP/матрицы/протокола; 44 executable из 132 |
| Acceptance | Пороги на frozen/GOLD с 95% CI | не измерены; 6 gold-позитивов < n=16 для recall |
| Production | OIDC, TLS, AV, backup, SLA | JWT containment и hardening контейнеров; не OIDC |

Конкурсный RC к 29.09.2026 — безопасный finalize, честный coverage, рекордер
Gate K, измеренный Gate L **без** production SLA. Полные 100% ТЗ без GOLD,
frozen val и пяти инспекторов **недостижимы**.

Программа работ: [`TZ_COMPLETION.md`](TZ_COMPLETION.md).
OSINT Document AI (срез 20.09.2026, не bake-off GOLD): [`RESEARCH_OSINT_2026.md`](RESEARCH_OSINT_2026.md).
Кластеры правил: [`extractor_families.json`](../data/matrix/extractor_families.json)
(группировка по `extractor.type`, не 132/132 executable).
Поштучный триаж семейств `exact_field` / `presence`:
[`EXTRACTOR_FAMILY_TRIAGE.md`](EXTRACTOR_FAMILY_TRIAGE.md) и
[`family_triage.json`](../data/matrix/family_triage.json). Разбивка сейчас:
`executable` 44, `extractor_missing` 83, `advisory` 1, `source_missing` 4.
