# Handoff для следующего ИИ

Машиночитаемый пакет — не scorecard приёмки. Гейты I/J/K **открыты**.
Инженерный замер Gate L на GitHub-hosted runner есть; production SLA нет.
Порог ТЗ не публиковать без нижней границы Wilson на held-out validation.

## Читать в этом порядке

1. [`AGENTS.md`](../AGENTS.md) — инварианты 1–14.
2. [`data/dataset/agent_handoff.json`](../data/dataset/agent_handoff.json) — гейты, запреты, команды.
3. [`data/matrix/coverage_snapshot.json`](../data/matrix/coverage_snapshot.json) — разбивка `executable` / `extractor_missing` (coverage, не вся матрица executable).
4. [`data/dataset/gold_inventory.json`](../data/dataset/gold_inventory.json) — публичный gold ≠ frozen val.
5. [`data/dataset/gold_evidence_files.json`](../data/dataset/gold_evidence_files.json) — какие PDF gold грузить: F0171 как PD, F0201 `RD_ID_MIXED` только как RD.
6. [`data/dataset/train_public_index_stats.json`](../data/dataset/train_public_index_stats.json) — 203 файла, стадии, join исходных PDF.
7. [`data/dataset/train_public_engineering.json`](../data/dataset/train_public_engineering.json) и `train_public_pred.jsonl` — gold-evidence прогон: 0 попаданий из 6. PD+RD загружены; L4: у ПД нет заполненной графы «Утвердил». Порог recall ТЗ не берётся и не публикуется.
8. [`docs/WORK_PLAN.md`](WORK_PLAN.md), [`docs/KNOWN_GAPS.md`](KNOWN_GAPS.md), [`docs/PR_QUEUE.md`](PR_QUEUE.md).

Пересборка: `python scripts/export_agent_dumps.py` или `make agent-dumps`.
Локальный скоринг: `python -m kontur.evaluation.train_public` (на Windows нет `make`).

## Что уже на `main`

Шаги 0–2 плана: HTTP-пайплайн, OCR fail-closed (`ocr_text` = `UNAVAILABLE`), очередь READY→VERIFYING→COMPLETED.
Шаг 3: harness `train_public.py`, gold MIXED→RD только для файлов из `gold_evidence_files.json`.
Прогон: `n_read=2` (F0171+F0201), стадии PD+RD, `hits=0`, `gold_finding_status` = `CLARIFICATION_REQUIRED` («PD: эталон без признака утверждения»).
F0201: заполненная графа «Утвердил» + ФИО → `APPROVED`. F0171: обложка тома, в штампе нет «утв.»/«Утвердил»+ФИО. Заголовок «Согласовано» не эталон.
Гейт J открыт. Wilson 6/6 всё равно ниже порога (нужно n≥16).
`GAP-K6-P95` закрыт живым k6 на GHA (100 VU × 60 с, n=6000, p95=18,26 мс). Это не production SLA.
HTTP-вход: проверенный JWT (RS256/ES256). Legacy `actor@object/ROLE` только при
`KONTUR_ALLOW_INSECURE_DEV_AUTH`. Статический публичный ключ ≠ OIDC/JWKS.

## Что нельзя

- Вливать `feat/ocr-gate-i-crop3x-oem1` и `feat/ocr-300dpi-step2-verifying` (усечённый `ocr_tesseract.py`).
- Открывать TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Речников для порогов.
- Закрывать `GAP-IOS4-VAL` по 15 строкам gold или SILVER CA.
- Ставить `ocr_text=AVAILABLE` без GOLD Wilson.
- Угадывать не-gold `RD_ID_MIXED` как RD+ID. Overlay `annotated_documents` не источник скоринга.
- Считать заголовок ГОСТ «Согласовано» / строку «ГИП» утверждением редакции.
- Писать `CONFIRMED_VIOLATION` автоматом или LLM.

## Следующие слайсы

1. GOLD OCR и frozen val: кодом гейты I и J не закрыть.
2. 5 инспекторов → `USABILITY_RESULTS.md` (гейт K / `RT-2609-21`).
3. pdfium в дочернем процессе (`GAP-ISOLATE`).
4. Признак утверждения ПД без ослабления инварианта 5 (не «ГИП» и не пустая графа).
5. Экстракторы точечно по списку `extractor_missing` в coverage snapshot.

Гейты I и J кодом не закрыть: нет GOLD OCR и нет frozen val на 106 критических.
