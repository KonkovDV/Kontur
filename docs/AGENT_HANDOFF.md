# Handoff для следующего ИИ

Машиночитаемый пакет — не scorecard приёмки. Гейты I/J/K/L **открыты**.
Порог ТЗ не публиковать без нижней границы Wilson на held-out validation.

## Читать в этом порядке

1. [`AGENTS.md`](../AGENTS.md) — инварианты 1–14.
2. [`data/dataset/agent_handoff.json`](../data/dataset/agent_handoff.json) — гейты, запреты, команды.
3. [`data/matrix/coverage_snapshot.json`](../data/matrix/coverage_snapshot.json) — разбивка `executable` / `extractor_missing` (coverage, не вся матрица executable).
4. [`data/dataset/gold_inventory.json`](../data/dataset/gold_inventory.json) — публичный gold ≠ frozen val.
5. [`data/dataset/train_public_index_stats.json`](../data/dataset/train_public_index_stats.json) — 203 файла, стадии, join исходных PDF.
6. [`data/dataset/train_public_engineering.json`](../data/dataset/train_public_engineering.json) и `train_public_pred.jsonl` — локальный прогон last-file-per-stage: 0 попаданий из 6 (Тюменская без RD/ID). Порог recall ТЗ не берётся и не публикуется.
7. [`docs/WORK_PLAN.md`](WORK_PLAN.md), [`docs/KNOWN_GAPS.md`](KNOWN_GAPS.md), [`docs/PR_QUEUE.md`](PR_QUEUE.md).

Пересборка: `python scripts/export_agent_dumps.py` или `make agent-dumps`.

## Что уже на `main`

Шаги 0–2 плана: HTTP-пайплайн, OCR fail-closed (`ocr_text` = `UNAVAILABLE`), очередь READY→VERIFYING→COMPLETED.
Шаг 3: harness `train_public.py` и снимок в `data/dataset/train_public_*.json*`.
0 попаданий из 6: у Тюменской нет RD/ID. Гейт J открыт. CI на `main` зелёный.

## Что нельзя

- Вливать `feat/ocr-gate-i-crop3x-oem1` и `feat/ocr-300dpi-step2-verifying` (усечённый `ocr_tesseract.py`).
- Открывать TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Речников для порогов.
- Закрывать `GAP-IOS4-VAL` по 15 строкам gold или SILVER CA.
- Ставить `ocr_text=AVAILABLE` без GOLD Wilson.
- Угадывать `RD_ID_MIXED` как RD+ID. Overlay `annotated_documents` не источник скоринга.
- Писать `CONFIRMED_VIOLATION` автоматом или LLM.

## Следующие слайсы

1. Живой k6 после пайплайна → строка в `PERFORMANCE.md` (не пустой `PARSING`).
2. 5 инспекторов → `USABILITY_RESULTS.md`.
3. Экстракторы точечно по списку `extractor_missing` в coverage snapshot.
4. Не угадывать MIXED: нужен ответ организатора или отдельный evidence-файл gold.

Гейты I и J кодом не закрыть: нет GOLD OCR и нет frozen val на 106 критических.
