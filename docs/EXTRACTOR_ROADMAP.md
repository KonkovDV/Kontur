# Дорожная карта экстракторов матрицы (после P0)

Цель: нарастить `executable` **без** маскировки `extractor_missing`. Порядок — по семействам из [`EXTRACTOR_FAMILY_TRIAGE.md`](EXTRACTOR_FAMILY_TRIAGE.md) и `data/matrix/family_triage.json`.

## Принципы

1. Один PR — одно семейство или узкий кластер кодов + тесты на synthetic/GOLD-прокси.  
2. Нет экстрактора → статус `extractor_missing` остаётся видимым в scorecard и UI.  
3. Не закрывать гейты I/J в docs, пока нет n и 95% CI.  
4. Не ломать durable/hardening: `wiring`, object store, auth/clamd gates, compose MinIO/clamav.

## Очередь (предложение)

| Волна | Семейство / кластер | Зачем | Зависимости |
|---|---|---|---|
| W1 | `exact_field` паспорта / шифра (уже частично) | EM ключевых полей | dual-read OCR |
| W2 | `presence` комплектности разделов | меньше ложных MISSING | каталог документов |
| W3 | `number` / `room_compare` (ИОС4) | gold-кандидаты | vector marks |
| W4 | enum / направленные (KR-*) | закрытие щелей executable | справочники |
| W5 | таблицы (`exact_field` tabulares) | после bake-off table stack | Docling/Camelot только с лицензией OK |

## Метрика прогресса

Только `coverage_counts` из `tz_scorecard.json` + число новых тестов семейства. Не «% ТЗ».

## Связь с питчем

См. [JURY_ONEPAGER.md](JURY_ONEPAGER.md) и [research/competitors/](research/competitors/): конкуренты с 99/132 — claims; мы растём очередью W1–W5.
