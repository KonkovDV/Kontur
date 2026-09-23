# План дальнейшей работы (с 21.09.2026)

Дедлайн подачи — 29.09.2026 23:59 МСК.

**Freeze инфраструктуры до подачи.** Новые production-компоненты
(Prometheus/Grafana/ELK, OIDC/JWKS, TLS, backup/DR, УКЭП, РиН без sandbox,
RabbitMQ 4.x, универсальный CV, VLM fine-tune) **не** на critical path.
Разрешены только исправления S0/S1. Следующая работа повышает шанс
обнаружить и доказать расхождение на конкурсном комплекте, а не зрелость
транспорта.

Конкурсный вертикальный срез: `PZ-001`, `KR-055`, `AR-041`, `IOS4-078`,
`IOS4-079`, один текстовый реквизит, missing stage, stale-revision.
Семейства экстракторов — не 103 одиночных правила. Гейты I/J кодом не закрыть.

Каждый шаг: `requirement` → `artifact` → `test` → `metric` → `stop_condition`.
Порог ТЗ не публикуется без нижней границы Wilson на held-out validation.

Источник ошибок аудита: [`AUDITOR_ERRATA.md`](AUDITOR_ERRATA.md).
Публичный gold ≠ frozen val: [`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md).
Три контура готовности (не порог ТЗ): [`TZ_SCORECARD.md`](TZ_SCORECARD.md),
[`TZ_COMPLETION.md`](TZ_COMPLETION.md).
OSINT / bake-off кандидаты: [`RESEARCH_OSINT_2026.md`](RESEARCH_OSINT_2026.md).
Снимки для следующего ИИ: [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md),
шина агентов: [`GH_AGENT_BUS.md`](GH_AGENT_BUS.md),
`python scripts/export_agent_dumps.py`.

## Принцип

Не наращивать скелет API. **Запускать каскад L1–L7** на загруженных PDF
(векторный слой). OCR в запросе — следующий слайс, не замена компаратора.
Автомат не пишет `CONFIRMED_VIOLATION`.

## Шаг 0 — пайплайн в HTTP (этот срез)

| | |
|---|---|
| requirement | После `POST /documents/upload` процесс не остаётся вечно в `PARSING`: PDF → токены → паспорт → `evaluate_rule` по скомпилированной матрице → `put_finding` → `READY` |
| artifact | `application/process_pipeline.py`, вызов из `ProcessWorkspace` / API |
| test | `test_process_pipeline.py`, `test_api.py`: READY, 0 человеческих вердиктов, протокол без нарушений |
| metric | Число правил = 132 прогона движка; coverage не переименовывается в «реализовано» |
| stop | Появление `CONFIRMED_VIOLATION` без инспектора; READY при нуле прогонов; OCR объявлен AVAILABLE |

Не закрывает гейты I/J/K/L. OCR capabilities остаются `UNAVAILABLE`.

## Шаг 1 — OCR в запросе (гейт I)

Срез на `main`: `ocr_tesseract.py` заполняет пустые raster-страницы
при наличии Tesseract; `evaluate_rule` зовёт **region-crop** как независимый
второй источник для `dual_read_required`. `ocr_text` = `MEASURED`: замер есть, порог не взят, гейт I открыт.
Harness: `make ocr-pilot` (Docker + Tesseract). SILVER, без Речникова.
Локальный прогон 23.09.2026: n=5935, gate_i_low≈0.434.
Повтор на `OBJ-VIOLATION-EXAMPLES` после замены двойников: n=3013, gate_i_low≈0.426.
Оба ниже порога приёмки. `ocr_text` = `MEASURED`, не `AVAILABLE`. Гейт I открыт.

| | |
|---|---|
| requirement | Страницы без текстового слоя идут в `RASTER_REGION_CROP`; dual-read на правилах с флагом; CA на пилоте 300 стр. |
| artifact | `ocr_region_crop` из `evaluate_rule`; `ocr_pilot.py`; не VLM |
| test | raster PDF → не violation; OCR disagreement → `ABSTAIN`; Речников не eligible |
| metric | CA, n, Wilson **95%** (`metrics.wilson`, z=1.96) на eligible SILVER `PDF_TEXT_LAYER`. Не `wilson(290,300)` |
| stop | CA verifier < 0,95; подбор порога по TEST_HIDDEN; `AVAILABLE` / «гейт закрыт» по SILVER |

## Шаг 2 — проводка READY → VERIFYING → COMPLETED (этот срез)

Срез на `main`: инспектор открывает очередь `POST /verify` (`READY`→`VERIFYING`),
закрывает `POST /complete` (`VERIFYING`→`COMPLETED`), затем `POST /finalize`.
Первый `review` из `READY` тоже открывает очередь. Автомат не пишет
`FINALIZED` / `VERIFYING` / `COMPLETED`.

| | |
|---|---|
| requirement | Инспектор открывает очередь (`VERIFYING`), закрывает кандидатов, перевод в `COMPLETED`, затем finalize |
| artifact | `POST /processes/{id}/verify`, `POST /complete`; не авто-FINALIZED |
| test | из READY нельзя finalize; CANDIDATE блокирует complete и finalize |
| metric | ручной протокол, не F1 |
| stop | автомат в `FINALIZED` |

## Шаг 3 — прогон TRAIN_PUBLIC без публикации порога

Срез на `main`: `train_public.py` читает `files_index.jsonl`, исходные PDF
(не overlay). Не-gold `RD_ID_MIXED`/`UNKNOWN` пропускаются. Gold-файлы из
`data/dataset/gold_evidence_files.json`: F0171 как PD, F0201 MIXED **только
как RD** (не ID и не оба). Пайплайн иначе — последний файл стадии, как в HTTP.
JSONL с `object_id`. `closes_gate_j` всегда false.
Локальный gold-evidence прогон: PD+RD загружены, 0/6 — у ПД нет заполненной
графы «Утвердил», компаратор не запускался. Это не «гейт закрыт».

| | |
|---|---|
| requirement | 203 файла открытого train через пайплайн; 6 матричных gold Тюменской — инженерный отчёт |
| artifact | `evaluation/train_public.py`; `out/train_public_pred.jsonl` вне git |
| test | `test_train_public.py`: `object_id`; 6/6 не закрывает Wilson; даже 16/16 на train не закрывает J |
| metric | только внутренняя; в README не писать |
| stop | закрытие `GAP-IOS4-VAL` по 15 строкам |

## Шаг 4 — гейт K

| | |
|---|---|
| requirement | 5 инспекторов, ≤3 клика, dry-run 132 на живых PDF ≤ 30 мин |
| artifact | `docs/USABILITY_RESULTS.md` |
| test | форма `USABILITY_PROTOCOL.md` заполнена |
| metric | клики и минуты, не F1 |
| stop | «рекордер есть» вместо пяти сессий |

## Шаг 5 — гейт L

Срез на `main`: workflow `gate-l-live-k6` поднимает Uvicorn, k6 делает
`POST /upload` scoped-токеном, затем 100 VU × 60 с на tagged `GET /status`.
Артефакт: SHA, стенд GHA, n, p50/p95/p99 в `docs/PERFORMANCE.md`.
`GAP-K6-P95` закрыт этим замером. Production SLA не обещается.
`closes_gate_l` в dump остаётся false: GHA ≠ конкурсный стенд.

| | |
|---|---|
| requirement | k6 100 VU / 60 с на живом API после пайплайна |
| artifact | строка в `PERFORMANCE.md`: стенд, SHA, n, p50/p95/p99 |
| test | `test_k6_script_contract.py`, `test_k6_summary.py`, workflow `status-load` |
| metric | p95 < 200 мс на теге `status`; error rate < 1% |
| stop | дешёвый прогон на пустом `PARSING` как «гейт закрыт»; GHA p95 как production SLA |

## Вне critical path (не делать вместо вертикального среза)

BERT/облачный LLM как вердикт; YAML-админка норм; Prometheus/ELK;
weekly fine-tune report; DWG; 133-е правило; GitHub-merge красных PR;
OIDC/JWKS; TLS termination; production backup/DR; 132/132 экстрактора;
УКЭП; реальный РиН без контракта; RabbitMQ 4.x; универсальный CV;
отдельный VLM fine-tune.

## Stop-conditions продукта

- Карантин скрытого теста открыт для порогов → стоп.
- Автомат записал `CONFIRMED_VIOLATION` → дефект S0.
- Overlay нормы меняет вердикт матрицы → стоп (ADR-0006).
- Публикация P/R/F1 без Wilson low и n → стоп.

## Неделя 23–29.09

Календарь ниже повторяет дни брифа. Числа покрытия сверены со снимком 23.09, не с текстом брифа: **44** executable, **83** extractor_missing, **1** advisory, **4** source_missing. README и `GH_SITUATION_2026_09_21.md` показывают те же 44 / 83 / 1 / 4. Гейты I, J, K и L открыты. При конфликте брифа с `AGENTS.md` или с неотвеченным вопросом 20–22 остаётся инвариант. Вопросы сформулированы в `QUESTIONS_TO_ORGANIZER.md` и не отправлены: репозиторий не пишет, что они ушли.

Политика утверждения — [ADR-0013](adr/0013-approval-sources-pending-written-answer.md). Gold TRAIN_PUBLIC остаётся 0/6. Даже если инспектор выберет том ПД F0171, IOS4-078 и IOS4-079 на этих PDF дают `LOW_QUALITY`: у якоря нет числа правила (сечение `A×B` или расход `м³/ч`) ни в одном окне. Шесть gold-проверок помечены как визуальная конфигурация листов, не как текстовое число. `ocr_text` = `MEASURED`, не `AVAILABLE`. OCR-ветки `16f3a06` и `2ddc2b3` не мержить. Разбор чертежа запущен: `drawing_analysis` = `DEGRADED`. На листах gold (ПД стр. 104 ↔ РД стр. 17 и ПД стр. 88 ↔ РД стр. 18) сетка PATH-штрихов сравнима, Jaccard 0.367 и 0.555. Это не кандидат и не попадание: порог под эти четыре листа не ставился, гейт I открыт.

На `main` сканер инъекций вызывается после `flatten_tokens` и пишет `injection_clean`. Вердикт он не меняет. #84 не закрыт.

### Д0, 23.09

| Шаг брифа | Состояние |
|---|---|
| Свести coverage в README и `GH_SITUATION` | Сделано: 44 / 83 / 1 / 4, совпадает с `coverage_snapshot.json` |
| Новые источники `approval_status` | Индекс, «В производство работ» и экспертиза остаются не-утверждением. Одна ПД без «не утв.» — `PACKAGE_DEFAULT` (ADR-0014). |
| `ocr_text` → `AVAILABLE` | Не делать. SILVER n=3013, gate_i_low≈0.426. В коде `MEASURED`, гейт I открыт |
| Три вопроса организатору | Текст вопросов 20–22 есть. Отправка — действие человека |

Exit дня: цифры не расходятся; эталон не ослаблен; карантин `РАЗМЕЧЕННЫЙ_TEST__213` закрыт.

### Д1, 24.09

Широта правил только новым экстрактором и фикстурами: equal, mismatch, missing source, not approved, revision conflict, OCR disagreement, unit conversion, соседнее нерелевантное число. Триаж 83 `extractor_missing` уже записан. Переименовать статус в `executable` нельзя. Цель брифа «не меньше 70 executable» не выполняется перекраской. Порядок семейств, если появится новый экстрактор: number, enum, exact_field, presence. Таблица и геометрия не обещаются на этой неделе.

Урок комплекта: разные шифры стадии резолвятся порознь (`resolve_heads_by_identity`). Правило берёт том своего раздела. Это не новый экстрактор и не прирост 44 executable.

Issue #75 на `main` (PR #88) — учебный срез пяти правил, не прогон скрытого теста.

### Д2, 25.09 — демо

Живой экран `web/src/LiveWorkspace.tsx`: загрузка по стадии, таблица комплекта, кнопка «Назначить эталоном», список находок, полоса «закрыто / осталось / не проверялось», три панели ПД / РД / ИД с PNG страницы и polygon. Учебный рекордер остаётся отдельным режимом. Пустая стадия — «нет фрагмента», не нарушение. Подтверждение не является кнопкой по умолчанию. Горячие клавиши C / R / Q. Массового подтверждения и массового отказа на живом экране нет. Отклонение поштучно, с `reason_code` и комментарием. `MISSING_EVIDENCE` подтвердить как нарушение нельзя.

`split()` в этот день не открывать: после RC freeze, без заглушки `evidence_group_id`. Протокол Приложения 2 и pull РиН не наращивать раньше окна из трёх панелей.

Exit пятницы: загрузил комплект по стадиям, увидел три панели с листом, назначил эталон или увидел отказ сервера, подтвердил одну находку, отклонил одну с причиной, скачал протокол JSON и журнал. Массового подтверждения нет. Сессия не закрывает Gate K. РиН на экране — `sync_state`, не ACK.

### Д3, 26.09

Вынос L1–L7 в существующий worker — только после окна Д2. Новый брокер не заводить. Метрики раздела 14 публиковать только с n, abstention и 95% CI на validation, разбитой по `object_id`. Своей frozen validation нет. Adversarial-пакет влит в #128 и не закрывает #80: нет skew, OCR-расхождения, VLM и запрета класть текст страницы в system prompt. Тест на вложения PDF не писать (`GAP-EMB`).

### Д4, 27.09

Gate K: рекордер есть, сессий 0. Пять сессий проводит человек. Сырые логи класть в репозиторий только после сессий. Публичный стенд — решение человека (риск R1): не выкладывать скрытый тест и не вычищать документы молча.

### Д5–Д6, 28–29.09

28.09 после 12:00 — только исправления дефектов. 29.09 подача до 20:00 МСК — действие человека. Если к вечеру 25.09 нет пути Д2, не начинать SUSPICION и дообучение.

### Что бриф предлагает, а репозиторий не делает до письменного ответа

| Пункт | Почему стоп |
|---|---|
| `РАЗМЕЧЕННЫЙ_TEST__213` как frozen val | Вопрос 20 не отправлен. Карантин |
| Индекс пакета, штамп «В производство работ», заключение экспертизы как approval | Вопрос 21 не отправлен. ADR-0007 и ADR-0013 |
| `ocr_text` в `AVAILABLE` или `MEASURED` | Нет GOLD Wilson. Старые OCR-ветки не мержить |
| executable за счёт перекраски триажа | Нет рабочего экстрактора и фикстур |
| Заглушка `split()` | `source_id` — file_id эталона, не id родителя |
| Гейт L закрыт замером k6 | `closes_gate_l` = false |
| Публичный стенд и отправка вопросов коммитом | Решение человека |
