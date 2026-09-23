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
второй источник для `dual_read_required`. `ocr_text` остаётся `UNAVAILABLE`.
Harness: `make ocr-pilot` (Docker + Tesseract). SILVER, без Речникова;
нижняя граница Wilson ниже порога приёмки. `ocr_text` остаётся `UNAVAILABLE`.

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

Приоритет: найти и доказать расхождение на разрешённом комплекте и показать это в демо. Транспорт не наращивать. Цифры ниже сверены со снимком 23.09: **44** executable, **83** extractor_missing, **1** advisory, **4** source_missing. Гейты I, J, K и L открыты. `ocr_text` остаётся `UNAVAILABLE`, пока нет Wilson на GOLD.

Цель «executable ≥ 70» не даёт права переименовать `extractor_missing`. Новое правило становится executable только с рабочим экстрактором и фикстурами. Триаж 83 правил уже записан: без `geometry`, подсчёта, таблицы по элементам и составного поля их не поднимать.

L4 не ослаблять. Пока нет письменного ответа по полям индекса, эталон — заполненная графа «Утвердил» + ФИО либо `POST .../revisions/{file_id}/select`. «Согласовано», ГИП и штамп «В производство работ» сами по себе не approval. Gold TRAIN_PUBLIC остаётся 0/6, пока у ПД F0171 нет этой графы.

`РАЗМЕЧЕННЫЙ_TEST__213` не открывать для порогов, пока вопрос 20 в `QUESTIONS_TO_ORGANIZER.md` не получил артефакт отправки. Вопросы 20–22 сформулированы и не отправлены.

`split()` не заменять заглушкой `evidence_group_id`. Демо раздела «три панели» его не требует. OCR-ветки `16f3a06` и `2ddc2b3` не мержить.

На `main` (срез `45b022e`) `scan_tokens_for_injection` ещё не импортирован в `process_pipeline.py`. Вызов после `flatten_tokens` и поле `injection_clean` — открытый [PR #120](https://github.com/KonkovDV/Kontur/pull/120). Штамп и статус находки там не меняются. Мержить #120 можно только без `Closes #84`: нет VLM, и текст страницы не должен попадать в system prompt.

Сквозной демо-путь важнее нового брокера: загрузка, эталон, карточка, решение инспектора, протокол. Трёх синхронных панелей ПД/РД/ИД в `web/` ещё нет: viewer двухпанельный. Массовое подтверждение допустимо только после этого окна; массовое отклонение не делать.

### Что из брифа 23.09 не берём

Бриф описывает неделю до подачи. При конфликте с `AGENTS.md` остаётся инвариант.

| Пункт брифа | Решение |
|---|---|
| `РАЗМЕЧЕННЫЙ_TEST__213` как frozen val | Карантин, пока вопрос 20 не отправлен и нет артефакта ответа |
| Эталон по штампу «В производство работ» или заключению экспертизы без фрагмента | Не approval. Вопрос 21 не отправлен |
| `ocr_text` в `AVAILABLE` / `MEASURED` | Остаётся `UNAVAILABLE`. Ветки `16f3a06` и `2ddc2b3` не мержить |
| executable ≥ 70 за счёт 83 разобранных правил | Только новый экстрактор и фикстуры. Триаж не перекрашивать |
| `split()` в демо 25.09 | После RC freeze. Заглушка `evidence_group_id` запрещена |
| Гейт L закрыт замером k6 | `closes_gate_l` = false |
| Вынести L1–L7 в worker до карточки | Сначала трёхпанельный путь и решения инспектора |
| Публичный стенд | Решение человека: репозиторий и набор данных |

Порядок до 25.09: не слать вопросы от имени репозитория без человека; не ослаблять L4; не объявлять OCR доступным; не закрывать #80 черновиком #115, пока CI не получил раннер. Сценарий демо (три панели, одно подтверждение, одно отклонение с причиной, протокол, честный экран coverage) — критерий пятницы, не заявление, что он уже проходит.

### Порядок дней

Каждый день двигает либо доказанное расхождение на разрешённом комплекте, либо сквозное демо. Транспорт, новый брокер и заглушка `split()` в этот календарь не входят.

| День | Делать | Не делать |
|---|---|---|
| 23.09 | Зафиксировать отказы брифа. Держать [PR #120](https://github.com/KonkovDV/Kontur/pull/120): сканер после `flatten_tokens`, `injection_clean`, вердикт прежний | Не писать `Closes #84`. Не считать `runner_id=0` зелёным CI |
| 24.09 | Три синхронные панели ПД / РД / ИД в `web/` рядом с карточкой правила. Пустая стадия — «нет фрагмента», не нарушение | Не выносить L1–L7 в worker до этого окна. Не делать массовое отклонение |
| 25.09 | Одно подтверждение инспектора, одно отклонение с причиной, протокол, экран coverage 44 / 83 / 1 / 4 | Не объявлять сценарий пройденным, пока его нет в UI |
| 26–28.09 | Сверка только на разрешённых PDF. Вопросы 20–22 отправляет человек, если решит | Не открывать `РАЗМЕЧЕННЫЙ_TEST__213`. Не ослаблять L4. Не перекрашивать 83 `extractor_missing` |
| 29.09 | Подача — действие человека | Публичный стенд и отправка вопросов не делаются коммитом |
