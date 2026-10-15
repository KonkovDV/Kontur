# HANDOFF — следующая квота (Kontur)

**Для:** другой аккаунт / следующий исполнитель  
**Дата среза:** 2026-10-15 (МСК)  
**main tip:** `fbfa548` — `feat(obs): §13 п.1 JSON-логи (топ-20 #18) (#363)`  
**Правило жюри:** матрица **59/132** — **не** наращивать presence/enum; honesty > рост.

## Уже в main (не переделывать)

| PR | Что |
|---|---|
| #358/#359/#360 | earlier slice |
| #362 | RiN-фильтр: allowlist `confirmed→CONFIRMED_VIOLATION`, `negative_verified→NEGATIVE_VERIFIED`; пустой/неизвестный статус **отбрасывается**; тест есть. Хэш — отфильтрованное тело; для уже финализированных outbox — только новые (не пересчитывать старые). |
| #361 | Completeness: `MISSING` / `STAGE_UPLOADED_NOT_VERIFIED` / `STAGE_PARTIAL_NOT_VERIFIED`; **нет** PRESENT; `counts_as_violation=false` |
| #364 | Finalize §9.3 (CANDIDATE→409, upload после FINALIZED→409, unfinalize без причины→422 + аудит) |
| #363 | JSON-логи §13 п.1 (топ-20 #18) |

## Открытые PR — мержить при зелёном CI

1. **[#365](https://github.com/KonkovDV/Kontur/pull/365)** `feat/storage-integrity-sha` — §13 п.8 ежедневный SHA-256 (топ-20 #20). Бриф: локально `/workspace/kontur-tz/out/BRIEF_LOGS_SHA_P18_20.md` (если нет — копия критериев ниже).
2. **[#366](https://github.com/KonkovDV/Kontur/pull/366)** `feat/metrics-prometheus-p19` — §13 п.4–5 `/metrics` + rabbitmq_prometheus (топ-20 #19). Бриф: `/workspace/kontur-tz/out/BRIEF_METRICS_P19.md`.

Порядок: дождаться green → factcheck Вани по URL → merge. Не заявлять ELK/алерты/Grafana «готовы», если в PR только `/metrics` + partial scorecard.

## HOLD

- **[#353](https://github.com/KonkovDV/Kontur/pull/353)** ClamAV 1.4→1.5 — **HOLD до после 30.10**. Смена движка/сигнатур перед демо; CI green ≠ поведение сканера в контейнере.

## Критерии #365 (SHA) — сжато

- Эталонные `file_hash` в реестре уже есть; нужен **ежедневный** job: store blob ↔ реестр.
- Обход от реестра (`process_files`/`files`), не S3 list.
- Расхождение → ERROR + аудит; schedule в compose (cron/timer/сервис).
- Не путать с `payload_sha256` outbox / evidence card hash.

## Критерии #366 (metrics) — сжато

- Gateway + backend `GET /metrics` (prom-client / prometheus_client).
- RPS, latency histogram (bucket 0.5s), 5xx; RabbitMQ depth (плагин/порт).
- Scorecard: `partial` с перечислением, не «интегрированы Prometheus/Grafana/ELK».
- Label `route` = шаблон, не сырой path.

## Опционально дальше (после #365/#366)

- Дожать п.10 протокол по `/workspace/kontur-tz/out/BRIEF_PROTOCOL_P10.md` (колонки export, карточки file_id/approval_status, perf ≤30 с assemble+render, p95 n≥30).
- П.13 RiN: `rin_client` как consumer outbox (TLS, Idempotency-Key) — M; inbox→SYNCED — L, отложить. Не заявлять exactly-once / «доставлено в RiN» по publisher confirm.
- Брифы Вани (локальный clone, не в git):  
  `BRIEF_PROTOCOL_P10.md`, `BRIEF_RIN_P13.md`, `BRIEF_FINALIZE_P12.md`, `BRIEF_LOGS_SHA_P18_20.md`, `BRIEF_METRICS_P19.md` под `/workspace/kontur-tz/out/`.

## Не делать

- Рост матрицы presence/enum до 30.10.
- Merge #353 до финала.
- Overclaim PRESENT / AUTO_NO_DIFFERENCE в RiN / exactly-once.
