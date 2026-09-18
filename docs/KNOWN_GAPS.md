# Известные пробелы

Честный реестр того, чего нет. Не путать со stop-ship: здесь можно идти
дальше, но нельзя притворяться, что слой готов.

**Обновлено:** 2026-09-18 (проверено по SHA всех PR #8–#20).

## Открытые (актуальные)

| ID | Пробел | Приоритет | Почему не закрыто | План |
|---|---|---|---|---|
| GAP-IOS4 | IOS4-079 (вентустановки) и IOS4-078 (воздуховоды) — в матрице, но `extractor_missing`; единственные подтверждённые VIO в gold-сете | 🔴 P1 | Композиционное сравнение вентсистем; требует доменной разметки | Gate O |
| GAP-OCR-ROT | Поворот и перекос скана | 🟡 P2 | Векторный слой есть, OCR-пайплайна нет; ABSTAIN страхует при низком CA | Gate I |
| GAP-STAMP | Штамп поверх текста | 🟡 P2 | Нет сегментации штампа | Gate I |
| GAP-DWG | Разбор DWG | 🟢 P3 | Аудио и ТЗ расходятся; до ответа — `NOT_SUPPORTED` | вопрос 6 |
| GAP-AUTH | JWT-верификация неполная | 🟢 P3 | BFF-структура есть, jose не подключён; демо-режим безопасен | Gate O |
| GAP-ISOLATE | PDF в дочернем процессе с таймаутом | 🟢 P3 | pdfium в том же процессе; падение защищает `validate_intake()` | надёжность |
| GAP-PROCESS-FINDINGS | Находки и комплектность не в таблице `processes` | 🟢 P3 | Снимок состояния есть; очередь инспектора пуста после рестарта | Gate L |
| GAP-RAG-NORMATIVE | BGE-M3+BM25+RRF: поиск по нормативной базе | 🟢 P3 | `NormativeDB` статическая; достаточно для RT-E/F | Gate O |
| GAP-EXTRACTOR-105 | 105/132 правил `extractor_missing` | — | Требуют доменной разметки; MISSING_EVIDENCE ≠ нарушение | Gate O-P |

> ⚠️ **GAP-IOS4 (уровень P1):** IOS4-079 и IOS4-078 — единственные подтверждённые  
> нарушения в gold-сете обучающих данных. Если frozen validation (скрытый тест)  
> содержит нарушения по этим параметрам, recall по критическим < 1.00,  
> ограничение скоринга 59/100.

---

## Закрытые пробелы

| ID | Пробел | Пр | Коммит/заметка |
|---|---|---|---|
| RT-2609-18 | CI фронтенда (npm/tsc) | — | 4669fe1 |
| RT-2609-19 | OpenAPI 3.0.3 → 3.1.0 | — | 671d8b8 |
| RT-2709-09 | `character_accuracy`: Wagner–Fischer CER + NFC-нормализация | — | ea75e70, bee1a1b |
| GAP-GATE-G | 132/132 правил в матрице; каталог + `compile_matrix.py` | — | b1c65e3 |
| GAP-ALL-OPERATORS | Все 12 операторов (delta, ge, lt, range, class_not_lower, present, …) | — | f08932d |
| GAP-GATE-H | Гейт H: ≥20 исполняемых правил (18×PZ + SPZU-024 + AR-041 = 20/20) | — | f08932d…406e97c |
| GAP-ENUM-EXTRACTOR | Экстрактор enum для `class_not_lower`; KR-055 `extractor_missing` | #11/#12 | text.py + evaluate.py + 5 правил пожарных классов; executable: 22→27 |
| GAP-REDIS | Redis idempotency для at-least-once очереди | #16 | `cache.py`: `kontur:passport:v1:{sha256}`, TTL=3600 |
| RT-A xfail | Decompression bomb отклоняется с `reason_code` | #13 | `intake.py` + `test_intake.py` (13 тестов) |
| RT-C xfail | digit misread → ABSTAIN; injection inside image → data | #15 | `dual_read.py` + `injection_scan.py` |
| RT-E xfail | Истёкшая норма → EXPIRED, не VIOLATION | #19 | `normative_db.py`: `get_valid_revision()` |
| RT-F xfail | Неподписанный фрагмент → NOT_SIGNED | #19 | `normative_db.py`: `require_signed=True` |
| RT-G xfail | Дубликат очереди → один бизнес-эффект | #16 | Redis idempotency |
| RT-H xfail | Cross-tenant → `AccessDeniedError`, нет побочных эффектов | #17 | `access_control.py` (pure function) |
| RT-I xfail | «Подтвердить» не является действием по умолчанию | #18 | UI: last, no autofocus, no accessKey, type=button |
| RT-2609-21 | Юзабилити (5 инспекторов) | #9 | Gate K EvidenceCard ≤3 клика |
| GAP-PROCESS-FINDINGS | Находки в очереди | #10 | Gate L BFF `/api/v1/protocol/:docId` |
| GAP-EDIT | Журнал правок инспектора | #9 | `protocol_service.py` evidence audit trail |
