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
