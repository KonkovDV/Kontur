# Известные пробелы

Честный реестр того, чего нет. Не путать со stop-ship: здесь можно идти
дальше, но нельзя притворяться, что слой готов.

| ID | Пробел | Почему не закрыто | Куда |
|---|---|---|---|
| RT-2609-21 | Замер юзабилити на 5 инспекторах | Форма есть, сессий нет | гейт K |
| GAP-OCR-ROT | Поворот и перекос скана | Векторный слой есть, OCR-пайплайна нет | гейт I |
| GAP-STAMP | Штамп поверх текста | Нет сегментации штампа | гейт I |
| GAP-DWG | Разбор DWG | Аудио и ТЗ расходятся; до ответа — `NOT_SUPPORTED` | вопрос 6 |
| GAP-ISOLATE | PDF в дочернем процессе с таймаутом | pdfium в том же процессе | надёжность |
| GAP-FREE-SEARCH | Free-search живёт реестром `MATRIX_GAP`, не правилом матрицы | нет артефакта ответа организатора, добавлять 133-е правило нельзя | вопрос организатору |
| GAP-CAP-OCR | OCR/таблицы/чертёж объявлены `UNAVAILABLE` в capabilities | bake-off есть, живого пайплайна в запросе нет | гейт I |
| GAP-SPLIT | `split()` бросает `NotImplementedError` | каждая часть требует собственной `evidence_group` | после RC freeze |

Adversarial: RT-A…RT-I закрыты регрессией. Дубль находки в процессе закрыт
`put_finding` по `evidence_group_id`.

`GAP-ISOLATE` не закрыт `pdf_guard`: `wait_for` / ThreadPool ограничивают ожидание,
но не убивают поток pdfium и не выносят разбор в дочерний процесс.

## Неофициальные пометки созвона

Канал, дата и идентификатор обращения в репозитории не зафиксированы —
это не ответы организатора. Черновик: PDF-first; аналоги стека допустимы
при OpenAPI; mock-адаптера РиН достаточно для архитектуры; лимиты — про
интерактивную загрузку; «нормы не анализируем». Фиксация — в
[QUESTIONS_TO_ORGANIZER.md](QUESTIONS_TO_ORGANIZER.md).

## Частично закрытые пробелы

| ID | Что сделано | PR |
|---|---|---|
| GAP-EDIT | `GET /audit` endpoint + rbac `getAuditLog` + `PostgresAuditStore` в `audit_log` | #42, #48 |
| GAP-PROCESS-FINDINGS | `MemoryProcessStore.save_finding/load_findings` + `PostgresProcessStore` + миграция | #40, #47 |
| GAP-IOS4-VAL | `evaluation/recall.py` + синтетический корпус 40 образцов; recall ≥ 0.80 на синтетике | #49 |

**Остаётся**: отдельный `user_action_log` для GAP-EDIT; frozen val корпус для GAP-IOS4-VAL.

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
