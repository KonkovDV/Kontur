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
8. [`docs/WORK_PLAN.md`](WORK_PLAN.md), [`docs/KNOWN_GAPS.md`](KNOWN_GAPS.md), [`docs/PR_QUEUE.md`](PR_QUEUE.md), [`docs/TZ_SCORECARD.md`](TZ_SCORECARD.md).

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
Разбор PDF — в дочернем процессе; таймаут убивает child, не поток API.
Контейнеры core/gateway: non-root 10001, read-only rootfs, `cap_drop: ALL`,
порты на loopback (PR #60). Повтор идентичной загрузки (hash+stage) не
открывает процесс заново и не гоняет pipeline; `FINALIZED` → 409.
`web/` и `gateway/` зафиксированы `package-lock.json`; CI frontend — `npm ci`.
Учебный рекордер Gate K в `web/` пишет JSON `kontur-usability-v1`; сессий нет,
`closes_gate_k` false. `MISSING_EVIDENCE` нельзя подтвердить как нарушение.
`main` по-прежнему без branch protection.
PostgreSQL `save()` финализации fail-closed (PR #64): без атомарной
материализации INSERT placeholder запрещён. Payload собирается в
application-слое, JSON пишется в той же транзакции, что и процесс;
`UNIQUE (object_id, version)`; повтор с тем же каноническим JSON идемпотентен,
расхождение — конфликт. Без `connection.transaction()` финализация отклоняется.
Поверх этого: advisory lock объекта, `FOR UPDATE` процесса/находок/протоколов,
`payload_sha256`, `integration_outbox` PENDING. Живого Postgres concurrency-теста
нет. Это не sandbox РиН.

Поставка 20.09.2026: в `files/` есть `ПАКЕТ_УЧАСТНИКАМ_БЕЗ_ОТВЕТОВ_v2.0`
(checksums 18/18) и распакованный объект `10_Полярная_25_СОШ1100к7` (~20,9 ГБ,
ПД/РД/ИД, без gold). Нет frozen val, GOLD OCR, объектов 11–18, SHA исходных
`.tar`, утверждённого ПД для F0171. Объект 10 не TRAIN_PUBLIC и не закрывает
гейт J. Закрытый zip организатора и `РАЗМЕЧЕННЫЙ_TEST__213` не открывать для порогов.

## Что нельзя

- Вливать `feat/ocr-gate-i-crop3x-oem1` и `feat/ocr-300dpi-step2-verifying` (усечённый `ocr_tesseract.py`).
- Открывать TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Речников для порогов.
- Распаковывать `ПАКЕТ_ОРГАНИЗАТОРА_ЗАКРЫТЫЙ_v2.0.zip` для порогов, prompt и regex.
- Считать пакет без ответов v2.0 frozen val или закрытием гейта J.
- Закрывать `GAP-IOS4-VAL` по 15 строкам gold или SILVER CA.
- Ставить `ocr_text=AVAILABLE` без GOLD Wilson.
- Угадывать не-gold `RD_ID_MIXED` как RD+ID. Overlay `annotated_documents` не источник скоринга.
- Считать заголовок ГОСТ «Согласовано» / строку «ГИП» утверждением редакции.
- Писать `CONFIRMED_VIOLATION` автоматом или LLM.
- Возвращать import-time monkeypatch `ProcessRecord` из закрытого PR #61.
- Возвращать экспериментальный PR #63: provenance в `finding_to_schema` не
  вырезать, infrastructure не импортирует `assemble_protocol`.

## Следующие слайсы

1. GOLD OCR и frozen val: кодом гейты I и J не закрыть.
2. Рекордер кликов в `web/`; 5 инспекторов → `USABILITY_RESULTS.md` (гейт K / `RT-2609-21` открыт).
3. Живые Postgres-тесты finalize (два клиента, crash) — см. [`TZ_COMPLETION.md`](TZ_COMPLETION.md).
4. Признак утверждения ПД без ослабления инварианта 5 (не «ГИП» и не пустая графа).
5. Экстракторы семействами по `extractor_families.json`, не по одному из 103.
6. JWKS/OIDC, TLS 1.3, антивирус, защита ветки `main` — не замена гейтов I/J/K.
7. Если PAT когда-либо светился в issue/PR/логе — отозвать в GitHub Settings
   → Developer settings → Personal access tokens; не вставлять токен в чат.

Гейты I и J кодом не закрыть: нет GOLD OCR и нет frozen val на 106 критических.
