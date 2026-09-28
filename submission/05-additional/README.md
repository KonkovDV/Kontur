# Дополнительные материалы

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/05-additional

Гейты I/J/K/L открыты. Числа ниже — публичная разметка разработки
и инженерные прогоны. Это не порог ТЗ.

## Замеры

| Число | Где | Чем не является |
|---|---|---|
| 55 / 72 / 1 / 4 из 132 | [`coverage_snapshot.json`](../../data/matrix/coverage_snapshot.json) | заявление, что все параметры исполняются |
| 0 из 6 и 0 из 4, оба режима; `unlabeled_positive` 0 | [`GOLD_DIAGNOSIS.md`](../../docs/GOLD_DIAGNOSIS.md), повтор на дереве `3bc590f`, запись манифеста `9bd8753` | порог раздела 14. Нижняя граница интервала Wilson при n=6 равна 0, верхняя 0,39 |
| OCR `MEASURED`, пилот SILVER, n=5935 | [`METRICS.md`](../../docs/METRICS.md) | порог Character Accuracy не ниже 0,95 |
| healthz 200 из tar, образ `b6645cd` | [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md) | прогон с вынутым кабелем |
| k6, `/status`, p95 около 18 мс, GitHub Actions | [`METRICS.md`](../../docs/METRICS.md) | промышленный SLA |

Остановка того прогона — «якорь или число не найдены». Помещение 600 в ответ
не вышло. Пороги комнат по нему не подбирались. `tz_recall_met` false.

## Пример JSON

Синтетический учебный комплект, не документы организатора.
Как собрать заново: `python scripts/export_submission_example.py`.

| Папка | Что показывает |
|---|---|
| [`unattended/`](examples/unattended/submission.json) | Пакет без инспектора: 132 строки `COMPARISON_IMPOSSIBLE`, `violation_count` 0. [Протокол](examples/unattended/protocol.json) |
| [`after_etalon_select/`](examples/after_etalon_select/submission.json) | Инспектор назначил `f-pd`. Три кода PZ-001, KR-055, AR-041 — `VIOLATION_PRESENT` с доказательством, внутри это `CANDIDATE`. Подтверждённых нарушений 0. [Протокол](examples/after_etalon_select/protocol.json) |

Пояснение — [`examples/README.md`](examples/README.md).

## CI

Ruleset `main-pr-and-ci`, id 23890545. Обязательны checks: `backend`,
`contracts`, `db`, `claims`, `frontend`, `container-config`, `container-core`,
`container-gateway`, `container-smoke`, `relay-container`, `sync-lifecycle-db`.
Зелёный прогон job `backend` — `conclusion=success`, `runner_id` не 0,
непустые `runner_name` и `steps`. Обязательных ревью 0. Это не закрытие гейтов.

## Ориентир, не замер Контура

Источники уже названы в документации репозитория. Цифры чужих работ
точностью Контура не являются.

| Источник | Зачем он здесь |
|---|---|
| AECV-Bench, arXiv:2601.04819 | Подсчёт объектов на плане слабый, такие правила остаются `extractor_missing` |
| Регрессия кириллицы PaddleOCR-VL-1.6 | Стек OCR не менялся, для кириллицы остаётся eslav PP-OCRv5 |
| OWASP LLM01:2025 | PDF — недоверенный вход. Модель не пишет `finding_status` |
| Интервал Wilson | При малом n интервал Вальда не используется |

## Не сделано

Пять сессий Gate K. Видео. Frozen validation. Разбор XML. `split()` ([#83](https://github.com/KonkovDV/Kontur/issues/83)).
Изоляция VLM ([#84](https://github.com/KonkovDV/Kontur/issues/84)). Живой ACK РиН.

| Материал | Роль |
|---|---|
| [`03-presentation/`](../03-presentation/README.md) | Папка для поля «Презентация»: PowerPoint и PDF |
| [`openapi.yaml`](../../contracts/openapi.yaml) | Контракт API |
| [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md) | Реестр пробелов |
