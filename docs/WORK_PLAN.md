# План дальнейшей работы (с 19.09.2026)

Дедлайн подачи — 29.09.2026 23:59 МСК. Бюджет: пайплайн на живых PDF,
затем I → J-инженерия → K → L. Всё вне этого режется.

Каждый шаг: `requirement` → `artifact` → `test` → `metric` → `stop_condition`.
Порог ТЗ не публикуется без нижней границы Wilson на held-out validation.

Источник ошибок аудита: [`AUDITOR_ERRATA.md`](AUDITOR_ERRATA.md).
Публичный gold ≠ frozen val: [`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md).

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

Срез на `main`: `ocr_tesseract.py` заполняет **пустые** raster-страницы
при наличии Tesseract; `ocr_text` остаётся `UNAVAILABLE`. PR #53 as-is
не вливался (красный CI, ложное закрытие гейта).

| | |
|---|---|
| requirement | Страницы без текстового слоя идут в `RASTER_REGION_CROP`; dual-read на правилах с флагом; CA на пилоте 300 стр. |
| artifact | вызов verifier из `process_pipeline`; не VLM |
| test | raster PDF → не пустой успех vector; dual-read disagreement → `ABSTAIN` |
| metric | CA, n, Wilson **95%** (`metrics.wilson`, z=1.96) на `ocr_pilot_20260811` (не Речников). Не `wilson(290,300)` без корпуса |
| stop | CA verifier < 0,95; подбор порога по TEST_HIDDEN; `AVAILABLE` без замера |

## Шаг 2 — проводка READY → VERIFYING → COMPLETED

| | |
|---|---|
| requirement | Инспектор открывает очередь (`VERIFYING`), закрывает кандидатов, перевод в `COMPLETED`, затем finalize |
| artifact | API-переход или кнопка UI; не авто-FINALIZED |
| test | из READY нельзя finalize; CANDIDATE блокирует finalize |
| metric | ручной протокол, не F1 |
| stop | автомат в `FINALIZED` |

## Шаг 3 — прогон TRAIN_PUBLIC без публикации порога

| | |
|---|---|
| requirement | 203 файла открытого train через пайплайн; 6 матричных gold Тюменской — инженерный отчёт |
| artifact | JSONL предсказаний с `object_id` (не TEST_HIDDEN) |
| test | `load_frozen_val_jsonl` требует `object_id`; 6/6 не закрывает Wilson recall |
| metric | только внутренняя; в README не писать |
| stop | закрытие `GAP-IOS4-VAL` по 15 строкам |

## Шаг 4 — гейт K

| | |
|---|---|
| requirement | 5 инспекторов, ≤3 клика, dry-run 132 на живых PDF ≤ 30 мин |
| artifact | `docs/USABILITY_RESULTS.md` |
| test | форма `USABILITY_PROTOCOL.md` заполнена |
| metric | клики и минуты, не F1 |
| stop | «форма есть» вместо сессий |

## Шаг 5 — гейт L

| | |
|---|---|
| requirement | k6 100 VU / 60 с на живом API после пайплайна |
| artifact | строка в `PERFORMANCE.md`: стенд, SHA, n, p50/p95/p99 |
| test | контракт скрипта уже в `backend/tests` |
| metric | p95 ≤ 200 мс на теге `status` |
| stop | дешёвый прогон на пустом `PARSING` как «гейт закрыт» |

## Вне critical path (не делать вместо шагов 0–5)

BERT/облачный LLM как вердикт; YAML-админка норм; Prometheus/ELK;
weekly fine-tune report; DWG; 133-е правило; GitHub-merge красных PR.

## Stop-conditions продукта

- Карантин скрытого теста открыт для порогов → стоп.
- Автомат записал `CONFIRMED_VIOLATION` → дефект S0.
- Overlay нормы меняет вердикт матрицы → стоп (ADR-0006).
- Публикация P/R/F1 без Wilson low и n → стоп.
