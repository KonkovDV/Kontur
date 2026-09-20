# Уроки AeroBIM, сентябрь 2026

Постоянная запись того, что перенесено в Контур как дисциплина, а не как
зависимость. `C:\AeroBIM` — донор решений, не submodule.

## Тишина не считается успехом

Слой, которого нет в запросе, объявляется `UNAVAILABLE` или `DEGRADED`.
`overall` комплекта считается по **живому** пути извлечения (сейчас
векторный текст). Отсутствующий OCR не прячется и не валит векторный
комплект: `GET /api/v1/system/capabilities` разделяет `overall` и
`health.failed`.

## Advisory не пишет вердикт

LLM/VLM — sidecar. Их `UNAVAILABLE` не делает `kit_blocked`. Статус
находки пишет компаратор; инспектор — единственный источник
`CONFIRMED_VIOLATION`.

## PDF: таймаут в дочернем процессе

Разбор PDF идёт в `spawn`-процессе (`pdf_guard.run_pdf_parse_sync`).
По истечении лимита дочерний процесс `terminate`/`kill`, поток API
не остаётся с живым pdfium. По истечении — `PdfParseTimeoutError`,
не пустой успех. `process_id` в исключении нет: это идентификатор сверки.

## Provenance — в схеме, не в UserWarning

`source_id` и `evidence_refs` опциональны в `finding.schema.json`
(`additionalProperties: false`). Предметная находка по-прежнему требует
`evidence_group_id`. Предупреждение интерпретатора не заменяет контракт.

## Free-search не 133-е правило

`data/matrix/free_search.json` — реестр `MATRIX_GAP`. Отдельный статус
находки и keyword-сканер без evidence не добавляются.
