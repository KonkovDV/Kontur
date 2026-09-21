# Известные пробелы

Честный реестр того, чего нет. Не путать со stop-ship: здесь можно идти
дальше, но нельзя притворяться, что слой готов.

| ID | Пробел | Почему не закрыто | Куда |
|---|---|---|---|
| RT-2609-21 | Замер юзабилити на 5 инспекторах | Рекордер кликов есть; сессий нет | гейт K |
| GAP-OCR-ROT | Поворот и перекос скана | OCR при `rotate ≠ 0` пропускается (пустые токены) | гейт I |
| GAP-STAMP | Штамп поверх текста | Нет сегментации штампа | гейт I |
| GAP-DWG | Разбор DWG | Аудио и ТЗ расходятся; до ответа — `NOT_SUPPORTED` | вопрос 6 |
| GAP-IOS4-VAL | Recall критических на frozen val не измерен | документы TRAIN_PUBLIC есть; frozen val на 132/106 нет (6 матричных позитивов, Wilson 6/6 ниже порога); gold-evidence: F0171 PD + F0201 MIXED-as-RD, 0/6 из‑за L4 (ПД без заполненной графы «Утвердил»); harness в `backend/tests/test_frozen_val.py` | гейт J |
| GAP-FREE-SEARCH | Free-search живёт реестром `MATRIX_GAP`, не правилом матрицы | нет артефакта ответа организатора, добавлять 133-е правило нельзя | вопрос организатору |
| GAP-CAP-OCR | OCR/таблицы/чертёж объявлены `UNAVAILABLE` в capabilities | region-crop dual-read в коде; Docker SILVER-замер порог не берёт; нет GOLD | гейт I |
| GAP-SPLIT | `split()` бросает `NotImplementedError` | каждая часть требует собственной `evidence_group` | после RC freeze |
| GAP-ETALON-UI | инспекторский выбор эталона есть в API, двухпанельного evidence UI нет | POST `.../revisions/{file_id}/select` не закрывает J | конкурсный срез |

Adversarial: RT-A…RT-I закрыты регрессией. Дубль находки в процессе закрыт
`put_finding` по `evidence_group_id`. Очередь после рестарта — `process_findings`,
комплектность на `processes`, журнал — `audit_log`.

Поставка организатора, публичный gold-seed и пакет без ответов v2.0 **не**
закрывают `GAP-IOS4-VAL`: см. [`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md) и
`data/dataset/gold_inventory.json`. На машине 20.09.2026 есть распакованный
объект 10 (без gold); нет архивов 11–18 и нет frozen val; OCR-пилот SILVER
порог не берёт.

## Неофициальные пометки созвона

Канал, дата и идентификатор обращения в репозитории не зафиксированы —
это не ответы организатора. Черновик: PDF-first; аналоги стека допустимы
при OpenAPI; mock-адаптера РиН достаточно для архитектуры; лимиты — про
интерактивную загрузку; «нормы не анализируем». Фиксация — в
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
| GAP-PROCESS-FINDINGS | Находки, файлы и комплектность переживают смену workspace; Postgres пишет `process_findings` / `process_files` | schema.sql |
| GAP-EDIT | Журнал REVIEW/FINALIZE/UNFINALIZE в `audit_log` и GET `/audit` | audit_store.py |
| GAP-HTTP-PIPELINE | POST /upload гоняет L1–L7 по векторному слою и ставит READY | process_pipeline.py |
| GAP-HTTP-VERIFY | READY→VERIFYING→COMPLETED по HTTP; finalize только из COMPLETED, не автомат | review.py / api.py |
| GAP-K6-P95 | Live `/status`: 100 VU × 60 с, n=6000, p95=18,26 мс, 0 ошибок; artifact workflow | PR #57 |
| GAP-JWT-VERIFY | Проверенный JWT RS256/ES256; dotted-токен не падает в legacy; k6 без plaintext | PR #58 |
| GAP-ISOLATE | PDF-разбор в spawn-процессе; таймаут terminate/kill дочернего, не поток API | pdf_guard.py |
