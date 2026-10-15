# Передача работы (Kontur)

**Для:** другой аккаунт / следующий исполнитель  
**Дата среза:** 2026-10-15 (МСК)  
**main tip (на момент среза):** `fbfa548` — `feat(obs): §13 п.1 JSON-логи (топ-20 #18) (#363)`  
**Правило жюри:** матрица **59/132** — **не** наращивать presence/enum; honesty > рост.  
**Внешнее ревью:** `REVIEW_PR365_367.md` (read-only, 15.10 ~21:20 МСК) — выводы ниже уже учтены.

## Уже в main (не переделывать)

| PR | Что |
|---|---|
| #358/#359/#360 | earlier slice |
| #362 | RiN-фильтр: allowlist `confirmed→CONFIRMED_VIOLATION`, `negative_verified→NEGATIVE_VERIFIED`; пустой/неизвестный статус **отбрасывается**; тест есть. Хэш — отфильтрованное тело; для уже финализированных outbox — только новые (не пересчитывать старые). |
| #361 | Completeness: `MISSING` / `STAGE_UPLOADED_NOT_VERIFIED` / `STAGE_PARTIAL_NOT_VERIFIED`; **нет** PRESENT; `counts_as_violation=false` |
| #364 | Finalize §9.3 (CANDIDATE→409, upload после FINALIZED→409, unfinalize без причины→422 + аудит) |
| #363 | JSON-логи §13 п.1 (топ-20 #18) |

## Открытые PR — статус по ревью

### [#365](https://github.com/KonkovDV/Kontur/pull/365) `feat/storage-integrity-sha` — **HOLD**

§13 п.8 daily SHA-256 (топ-20 #20). CI green, код S ок, но **не мержить** как «п.8 закрыт».

**Findings (REVIEW_PR365_367):**
- **P0:** на Postgres CLI всегда `exit 2` — сверка на стенде фактически не выполняется (`scripts/check_storage_integrity.py`). При этом TZ_GAP_CLOSURE / docs подают п.8 закрытым → overclaim.
- P1: in-memory 0 файлов → exit 0 (вакуумный pass); для cron fail-closed нужен exit≠0 или флаг.
- P1: CLI не передаёт `audit=` → в проде нет `STORAGE_INTEGRITY_MISMATCH` audit.
- P1: пустой `file_hash` молча skip — не fail-closed.
- nit: **расписания в compose/timer нет** (только пример cron в docs) — не считать «schedule в compose» сделанным.

**NEXT для #365:** статус `partial (логика+тест; PG list-all и расписание — follow-up)` в TZ_GAP_CLOSURE/TZ_TRACEABILITY **или** добить `list_all_files()` для PG; затем уже merge. **Не merge-when-green.**

### [#366](https://github.com/KonkovDV/Kontur/pull/366) `feat/metrics-prometheus-p19` — **OK после P1 (P0 нет)**

§13 п.4–5 `/metrics` + rabbitmq_prometheus. Scorecard честно `partial`.

**Findings (REVIEW_PR365_367) — P1 до merge или сразу follow-up:**
- `route` = нормализованный **сырой** path, **не** шаблон FastAPI/Express: UUID/числа/hex режутся, но `f-xxx` / имена файлов / 404-сканы → cardinality. Фикс: `route="unmatched"` для неизвестных + allowlist `/api/v1/*`.
- Gateway `/metrics` без auth на `${KONTUR_BIND}:3000` — при `0.0.0.0` публично. Токен / bind 127.0.0.1 / отдельный порт.
- `kontur_findings_total` / `kontur_processing_seconds` объявлены, но `note_*` **нигде не вызываются** → пустые серии; убрать из docs или подключить. Outbox backlog из брифа — deferred.

**Не заявлять:** ELK / алерты / Grafana «готовы»; `route=шаблон` — пока не пофикшено.

## HOLD (демо)

- **[#353](https://github.com/KonkovDV/Kontur/pull/353)** ClamAV 1.4→1.5 — **HOLD до после 30.10**. Смена движка/сигнатур перед демо; CI green ≠ поведение сканера в контейнере.

## Критерии #365 (SHA) — сжато / актуально

- Обход от реестра (`process_files`/`files`), не S3 list — **есть**.
- Расхождение → ERROR (+ ideally audit) — логика есть; audit в CLI и PG path — **дыры**.
- Расписание в compose/cron/timer — **нет** (только docs-пример).
- Не путать с `payload_sha256` outbox / evidence card hash.

## Критерии #366 (metrics) — сжато / актуально

- Gateway + backend `GET /metrics` — есть; scorecard `partial`.
- RPS, latency histogram (0.5s), 5xx; RabbitMQ depth (плагин/порт 15692) — есть.
- Label `route` = **шаблон** — **ещё нет** (сейчас сырой path после regex).
- Findings counters wired — **ещё нет**.

## Опционально дальше (после фикса #365/#366)

- П.10 протокол: колонки export, карточки `file_id`/`approval_status`, perf ≤30 с assemble+render, p95 n≥30 (`BRIEF_PROTOCOL_P10`).
- П.13 RiN: `rin_client` consumer outbox (TLS, Idempotency-Key) — M; inbox→SYNCED — L. Не exactly-once / «доставлено в RiN» по publisher confirm.
- Брифы (локально у ревьюера, не в git): `BRIEF_PROTOCOL_P10`, `BRIEF_RIN_P13`, `BRIEF_FINALIZE_P12`, `BRIEF_LOGS_SHA_P18_20`, `BRIEF_METRICS_P19`, `REVIEW_PR365_367`.

## Не делать

- Рост матрицы presence/enum до 30.10.
- Merge #353 до финала.
- Merge #365 как «п.8 закрыт» / merge-when-green без PG wiring или явного `partial` в gap-docs.
- Overclaim PRESENT / AUTO_NO_DIFFERENCE в RiN / exactly-once / `route=template` до фикса.
