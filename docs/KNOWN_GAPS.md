# Известные пробелы

Честный реестр того, чего нет. Не путать со stop-ship: здесь можно идти
дальше, но нельзя притворяться, что слой готов.

| ID | Пробел | Почему не закрыто | Куда |
|---|---|---|---|
| RT-2609-21 | Замер юзабилити на 5 инспекторах | Рекордер кликов есть; сессий нет | гейт K |
| GAP-OCR-ROT | Поворот и перекос скана | Полный лист с `/Rotate` читается: bitmap pdfium уже вид страницы. Если при `rotate=0` прямой OCR пуст, пробуются 90/180/270. Кроп значения при `rotate ≠ 0` по-прежнему пуст. Гейт I открыт | гейт I |
| GAP-STAMP | Штамп поверх текста | Нет сегментации штампа | гейт I |
| GAP-DWG | Разбор DWG | Ответ организатора 26.09.2026: обработку DWG реализовывать не требуется. Вход MVP — PDF и DOCX; XML принимается по контракту | закрыт как не требуемый |
| GAP-IOS4-VAL | Recall критических на frozen val не измерен | документы TRAIN_PUBLIC есть; frozen val на 132/106 нет (6 матричных позитивов, Wilson 6/6 ниже порога); gold-evidence: F0171 PD + F0201 MIXED-as-RD, прогон 24.09 — 0/6, IOS4-078/079 `LOW_QUALITY` («якорь или число не найдены»), не L4; harness в `backend/tests/test_frozen_val.py` | гейт J |
| GAP-FREE-SEARCH | Free-search живёт реестром `MATRIX_GAP`, не правилом матрицы | нет артефакта ответа организатора, добавлять 133-е правило нельзя | вопрос организатору |
| GAP-CAP-OCR | OCR `MEASURED`, таблицы `UNAVAILABLE`, чертёж `DEGRADED` | SILVER n=3013, gate_i_low≈0.426, порог 0.97 не взят. Не GOLD. Гейт I открыт | гейт I |
| GAP-OCR-RASTER | Нет человечески проверенного эталона страниц без текстового слоя | Пилот SILVER — это PDF_TEXT_LAYER. Подписи растра не выдумывать. В образ ядра на сборке кладутся веса eslav PP-OCRv5 ONNX со сверкой SHA-256; без каталога остаётся Tesseract. `ocr_text` остаётся `MEASURED` | гейт I |
| GAP-SPLIT | `split()` бросает `NotImplementedError` | каждая часть требует собственной `evidence_group` | после RC freeze |
| GAP-ETALON-UI | кнопка «Назначить эталоном» есть на живом экране комплекта | POST `.../revisions/{file_id}/select` из READY и VERIFYING, пока нет решений инспектора; штамп «не утв.» не перекрывается. Gate J открыт | конкурсный срез |
| GAP-EMB | Вложения PDF `/EmbeddedFile` | Пайплайн их не читает. Тест на `FPDFDoc_GetAttachmentCount` не писать | #80 |
| GAP-INJ-SCAN | Сканер инъекций вызывается после `flatten_tokens` и пишет `injection_clean` | Статус находки не меняется. Текст страницы не инструкция. #84 не закрыт: нет VLM и нет system prompt | #84 |
| GAP-PROTOCOL-PDF | PDF протокола | закрыт: reportlab и шрифт DejaVu/Arial, тот же провод, что DOCX. WeasyPrint не используется | Приложение 2 |

Adversarial: RT-A…RT-I закрыты регрессией. Дубль находки в процессе закрыт
`put_finding` по `evidence_group_id`. Очередь после рестарта — `process_findings`,
комплектность на `processes`, журнал — `audit_log`.
GAP-EMB: вложения `/EmbeddedFile` пайплайн не видит (см. таблицу выше).

Поставка организатора, публичный gold-seed и пакет без ответов v2.0 **не**
закрывают `GAP-IOS4-VAL`: см. [`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md) и
`data/dataset/gold_inventory.json`. На машине 20.09.2026 есть распакованный
объект 10 (без gold); нет архивов 11–18 и нет frozen val; OCR-пилот SILVER
порог не берёт.

## Ответы организатора 26.09.2026

Сводная таблица получена в рабочий контур. Канал, дата и идентификатор
отправки вопросов 1–22 из этого репозитория по-прежнему не зафиксированы.
Текст ответов — [`ORGANIZER_ANSWERS_2026_09_26.md`](ORGANIZER_ANSWERS_2026_09_26.md).
Черновик созвона в `QUESTIONS_TO_ORGANIZER.md` эту таблицу не подменяет.

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
| GAP-IOS4 | IOS4-078/079 остаются `number`. Тип `geometry` меряет пару штрихов в оценке и не включён в матрицу | synthetic |
| GAP-RT-G | Дубль находки в процессе: `put_finding` по evidence_group_id | runtime.py |
| GAP-PROCESS-FINDINGS | Находки, файлы и комплектность переживают смену workspace; Postgres пишет `process_findings` / `process_files` | schema.sql |
| GAP-EDIT | Журнал REVIEW/FINALIZE/UNFINALIZE в `audit_log` и GET `/audit` | audit_store.py |
| GAP-HTTP-PIPELINE | POST /upload гоняет L1–L7 по векторному слою и ставит READY | process_pipeline.py |
| GAP-HTTP-VERIFY | READY→VERIFYING→COMPLETED по HTTP; finalize только из COMPLETED, не автомат | review.py / api.py |
| GAP-K6-P95 | Live `/status`: 100 VU × 60 с, n=6000, p95=18,26 мс, 0 ошибок; artifact workflow | PR #57 |
| GAP-JWT-VERIFY | Проверенный JWT RS256/ES256; dotted-токен не падает в legacy; k6 без plaintext | PR #58 |
| GAP-ISOLATE | PDF-разбор в spawn-процессе; таймаут terminate/kill дочернего, не поток API | pdf_guard.py |
