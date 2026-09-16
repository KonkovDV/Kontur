# Матрица контроля

Источник — Приложение 1 организатора и его машиночитаемый дубль
`source/parameter_catalog_132.jsonl` (132 строки, коды `PZ-001` … `SM-132`).
`matrix_version: draft-0` до подтверждения, что xlsx — подписанное приложение.

Пересборка: `python scripts/compile_matrix.py`. Ручные экстракторы не живут
в `rules/` напрямую — только в `overrides/`; иначе генератор их затрёт.

## Структура

```text
source/parameter_catalog_132.jsonl  каталог организатора, без правок
params.template.csv                 таблица Params (ТЗ п. 8.1) + legal_criticality
overrides/<CODE>.json               ручной экстрактор/компаратор/фикстуры
rules/<CODE>.json                   скомпилированное правило (rule.schema.json)
free_search.json                    находки вне реестра 132 (не правила матрицы)
sections.json                       соответствие разделов ПД/РД/ИД (ТЗ п. 6)
```

Короткие формы из Приложения 2 (`AR-14`) — display-алиасы.
`FileRuleRegistry.get("AR-14")` возвращает `AR-014`.

## Процедура добавления параметра

1. Строка Приложения 1 попадает в каталог; `compile_matrix.py` пишет CSV и скелет.
2. Текстовый `trigger_logic` компилируется в Rule DSL. Ручной override —
   только если скелета мало; черновик обязателен к юридической проверке (ADR-0004).
3. Правило получает минимум четыре фикстуры. Правило без фикстур не в релизе.
4. `coverage` честный. `executable` — только при рабочем экстракторе.
   Сейчас все 132 строки — `extractor_missing`.

## Вне матрицы

`FREE-HEATING-001` (тёплые полы, GOLD VIO-0002) в 132 параметрах нет.
Это `matrix_scope: FREE_SEARCH`, не 133-я строка и не молчаливая правка матрицы.

## Отчёт покрытия

`coverage_report` публикуется в разбивке
`executable / extractor_missing / source_missing / advisory / not_applicable`.
Формулировка «реализовано 132 параметра» без этой разбивки запрещена.
