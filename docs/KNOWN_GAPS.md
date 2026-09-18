# Известные пробелы

Честный реестр того, чего нет. Не путать со stop-ship: здесь можно идти
дальше, но нельзя притворяться, что слой готов.

| ID | Пробел | Почему не закрыто | Куда |
|---|---|---|---|
| RT-2609-21 | Замер юзабилити на 5 инспекторах | Форма есть, сессий нет | гейт K |
| GAP-PROCESS-FINDINGS | Находки и комплектность не в таблице `processes` | Снимок состояния есть; очередь инспектора после рестарта пуста | гейт L |
| GAP-OCR-ROT | Поворот и перекос скана | Векторный слой есть, OCR-пайплайна нет | гейт I |
| GAP-STAMP | Штамп поверх текста | Нет сегментации штампа | гейт I |
| GAP-DWG | Разбор DWG | Аудио и ТЗ расходятся; до ответа — `NOT_SUPPORTED` | вопрос 6 |
| GAP-EDIT | Журнал правок инспектора отдельной таблицей | Решение пишется в находку, отдельного `user_action_log` нет | гейт K |
| GAP-ISOLATE | PDF в дочернем процессе с таймаутом | pdfium в том же процессе | надёжность |
| GAP-IOS4-VAL | IOS4-078/079 executable на синтетике; recall на frozen val не измерен | экстрактор берёт первую сторону сечения, не площадь мм² | гейт J |
| GAP-FREE-SEARCH | Free-search живёт реестром `MATRIX_GAP`, не правилом матрицы | нет артефакта ответа организатора, добавлять 133-е правило нельзя | вопрос организатору |
| GAP-CAP-OCR | OCR/таблицы/чертёж объявлены `UNAVAILABLE` в capabilities | bake-off есть, живого пайплайна в запросе нет | гейт I |
| GAP-SPLIT | `split()` бросает `NotImplementedError` | каждая часть требует собственной evidence_group | после RC freeze |

Adversarial: RT-A…RT-I закрыты регрессией. Дубль находки в процессе закрыт
`put_finding` по `evidence_group_id`; протокол/находки после рестарта — GAP-PROCESS-FINDINGS.

`GAP-ISOLATE` не закрыт `pdf_guard`: `wait_for` / ThreadPool ограничивают ожидание,
но не убивают поток pdfium и не выносят разбор в дочерний процесс.

## Red Team фактчекинг PR #36 (2026-09-18)

PR #36 содержал 6 критических несоответствий реальному API main:

| ID | Фактчекинг | Правда |
|---|---|---|
| RT-1 | `engine_health_summary` — плоский словарь {name: label} | Нет. API: {healthy/degraded/failed/skipped: list[str]} |
| RT-2 | `/capabilities` ключи overall_kit_status, engine_status | Нет. Ключи: overall, kit_blocked, engines, health |
| RT-3 | `/capabilities` вызывался без auth | Нет. 401 без токена |
| RT-4 | `parse_with_timeout()`, `process_id` поле | Нет. API: `run_pdf_parse_sync(parser, data)`, нет `process_id` |
| RT-5 | `overall_kit_status == "BLOCKED"` | Нет. Значения: AVAILABLE/DEGRADED/UNAVAILABLE |
| RT-6 | UserWarning из Finding | Нет. Нет UserWarning в __post_init__ |

## Триаж: что взяли, что нет

| Область | Взяли (4c1c518) | Не взяли / Почему |
|---|---|---|
| Capabilities | kit_degraded + engine_health_summary + overall_kit_status + /capabilities endpoint | Дубль engine_status.py |
| Provenance | Finding.source_id + evidence_refs + DisagreementKind (схема) | UserWarning (не в коде) |
| PDF | run_pdf_parse + run_pdf_parse_sync + shutdown(wait=False) | process_id на таймауте |
| IOS4 | dual-read + E2E ABSTAIN на двух сечениях | Площадь мм² (GAP-IOS4-VAL, Gate J) |
| Frozen val | skip без корпуса | Recall/P/F1 |
| Free-search | Загрузчик реестра MATRIX_GAP | 133-е правило |

## Неофициальные пометки созвона

Канал, дата и идентификатор обращения в репозитории не зафиксированы —
это не ответы организатора. Черновик: PDF-first; аналоги стека допустимы
при OpenAPI; mock-адаптера РиН достаточно для архитектуры; лимиты про интерактивную загрузку;
«нормы не анализируем». Фиксация — в
[QUESTIONS_TO_ORGANIZER.md](QUESTIONS_TO_ORGANIZER.md).

## Закрытые пробелы

| ID | Закрыт | Коммит |
|---|---|---|
| RT-2609-18 | CI фронтенда (npm/tsc) | 4669fe1 |
| RT-2609-19 | OpenAPI 3.0.3 → 3.1.0 | 671d8b8 |
| RT-2709-09 | character_accuracy: Wagner–Fischer CER + NFC-нормализация | ea75e70, bee1a1b |
| GAP-GATE-G | 132/132 правил в матрице; каталог + compile_matrix.py | b1c65e3 |
| GAP-ALL-OPERATORS | Все 12 операторов (delta, ge, lt, range, class_not_lower, present, …) | f08932d |
| GAP-GATE-H | Гейт H: ≥20 исполняемых правил (18×PZ + SPZU-024 + AR-041 = 20/20) | f08932d…406e97c |
| GAP-ENUM-EXTRACTOR | text/enum экстрактор; KR-055 и PZ-015/021/022/023 executable | 4a10ce8 |
| GAP-IOS4 | IOS4-078/079: number-экстрактор, synthetic E2E | overrides + compile |
| GAP-RT-G | Дубль находки в процессе: `put_finding` по evidence_group_id | runtime.py |
