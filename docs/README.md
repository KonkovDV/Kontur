# Карта документов

Учебный стенд поднимается и проводит комплект до протокола. Приёмка по гейтам I, J, K и L ещё впереди. Покрытие матрицы: 59 executable, 68 `extractor_missing`, 1 advisory, 4 `source_missing`. Эти числа стоят в [`TZ_SCORECARD.md`](TZ_SCORECARD.md) и в [`../README.md`](../README.md). В планах сентября покрытие другое — там снимок того дня.

Ниже каждый файл отвечает на один вопрос.

| Вопрос | Тип | Куда |
|---|---|---|
| Как пройти учебный комплект от кнопки до протокола | учебник | [`../submission/04-prototype/README.md`](../submission/04-prototype/README.md), сценарий в [`../README.md`](../README.md) |
| Как поднять, остановить, посчитать пакет | инструкция | [`../README.md`](../README.md) разделы запуска и пакетного прогона, [`GATE_L_RUNBOOK.md`](GATE_L_RUNBOOK.md) |
| Где контракт, правило, пункт ТЗ | справочник | [`../contracts/openapi.yaml`](../contracts/openapi.yaml), [`../data/matrix/README.md`](../data/matrix/README.md), [`TZ_TRACEABILITY.md`](TZ_TRACEABILITY.md), [`MODULES.md`](MODULES.md) |
| Почему редакция, триггер и вердикт устроены так | объяснение | [`../README.md`](../README.md) раздел «Редакция и знак триггера», [`adr/`](adr/), [`SOTA_AEROBIM_ANALYSIS.md`](SOTA_AEROBIM_ANALYSIS.md) |

## Приёмка

| Вопрос | Файл |
|---|---|
| Одностраничник и вопросы на защите | [`JURY_ONEPAGER.md`](JURY_ONEPAGER.md) |
| Очередь экстракторов после P0 | [`EXTRACTOR_ROADMAP.md`](EXTRACTOR_ROADMAP.md) |
| Четыре входа, без обхода репозитория | [`../README.md`](../README.md), раздел «Куда смотреть» |
| Пакет поставки | [`../submission/README.md`](../submission/README.md) |
| Постановка и методология | [`../submission/02-documentation/README.md`](../submission/02-documentation/README.md) |
| Замеры | [`../submission/05-additional/README.md`](../submission/05-additional/README.md) |
| Экран инспектора | [`../web/README.md`](../web/README.md) |

## Статус

| Вопрос | Файл |
|---|---|
| Три контура, не один процент | [`TZ_SCORECARD.md`](TZ_SCORECARD.md), [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| n и интервал | [`METRICS.md`](METRICS.md) |
| Почему 28.09 записано 0 из 6, а 08.10 — 6 из 6 | [`GOLD_DIAGNOSIS.md`](GOLD_DIAGNOSIS.md), [`METRICS.md`](METRICS.md) |
| Открытые пробелы | [`KNOWN_GAPS.md`](KNOWN_GAPS.md) |
| OCR | [`OCR_BAKEOFF.md`](OCR_BAKEOFF.md) |
| Нагрузка, логи, целостность хранилища | [`PERFORMANCE.md`](PERFORMANCE.md), [`OBSERVABILITY.md`](OBSERVABILITY.md), [`STORAGE_INTEGRITY.md`](STORAGE_INTEGRITY.md) |
| Атаки и stop-ship | [`RED_TEAM.md`](RED_TEAM.md), [`RED_TEAM_TRIAGE.md`](RED_TEAM_TRIAGE.md) |

## Объяснение текущего поведения

| Тема | Файл |
|---|---|
| Редакция до сравнения. Пустой шифр собирает цепочку ПД и РД по имени | [`adr/0003-revision-resolver-before-comparison.md`](adr/0003-revision-resolver-before-comparison.md) |
| Штамп: угол 190×70 мм, графа «Лист», буква стадии П, Р или И | [`ARCHITECTURE.md`](ARCHITECTURE.md#редакция-штамп-и-знак-триггера) |
| Знак триггера, единицы, десятичная разность, невидимый текст | [`SOTA_AEROBIM_ANALYSIS.md`](SOTA_AEROBIM_ANALYSIS.md) |
| Модель не пишет статус | [`adr/0001-llm-never-sets-verdict.md`](adr/0001-llm-never-sets-verdict.md) |
| Сверка документов, не нормы | [`adr/0006-compare-documents-not-norms.md`](adr/0006-compare-documents-not-norms.md) |
| Остальные решения | [`adr/`](adr/) |


## Исследование

| Вопрос | Файл |
|---|---|
| Смежные открытые репозитории (18.10.2026) | [`research/competitors/OSINT-2026-10-18.md`](research/competitors/OSINT-2026-10-18.md) |
| Смежные репозитории, срез 15.10.2026 | [`research/competitors/`](research/competitors/) |
| OCR / Document AI (срез 28.09) | [`RESEARCH_OSINT_2026.md`](RESEARCH_OSINT_2026.md) |

## Записи по дням

Дата в имени файла — день записи. Текущее покрытие смотрите в scorecard.

| Запись | Файл |
|---|---|
| План 26–29.09 | [`PLAN_2026_09_26_29.md`](PLAN_2026_09_26_29.md) |
| План 28–29.09 | [`PLAN_2026_09_28_29.md`](PLAN_2026_09_28_29.md) |
| Ответы организатора 26.09 | [`ORGANIZER_ANSWERS_2026_09_26.md`](ORGANIZER_ANSWERS_2026_09_26.md) |
| Холодный запуск 27–28.09 | [`DEMO_COLD_START.md`](DEMO_COLD_START.md) |
