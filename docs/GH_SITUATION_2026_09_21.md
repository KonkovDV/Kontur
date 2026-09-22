# Срез ситуации Kontur — 21.09.2026

Документ для ИИ, который заходит **только через GitHub** (clone `main`, Issues, PR).
Не frozen val, не GOLD OCR, не scorecard приёмки ТЗ и не заявление, что
вся матрица executable.

- Репозиторий: https://github.com/KonkovDV/Kontur (private)
- Дедлайн подачи: **29.09.2026 23:59 МСК**
- Задача №10 ЛЦТ, Мосгосстройнадзор: сверка ПД↔РД↔ИД по матрице 132 параметров
- Имя продукта в UI: «Инспектор ИИ». Кодовая линия: Контур
- Ветки: рабочая линия `main`. OCR-хвосты не мержить. Dependabot PR (#85) не P0

Машиночитаемый twin: [`data/dataset/agent_handoff.json`](../data/dataset/agent_handoff.json).
Операционный handoff: [`AGENT_HANDOFF.md`](AGENT_HANDOFF.md).
Инварианты: [`../AGENTS.md`](../AGENTS.md).
Шина нескольких ИИ: [`GH_AGENT_BUS.md`](GH_AGENT_BUS.md) (Issues + `gh`, не Discussions).

## Как читать (порядок)

1. Этот файл.
2. [`../AGENTS.md`](../AGENTS.md) — 14 инвариантов.
3. [`GH_AGENT_BUS.md`](GH_AGENT_BUS.md) — claim / DAG / cloud vs local.
4. [`data/dataset/agent_handoff.json`](../data/dataset/agent_handoff.json).
5. [`data/matrix/coverage_snapshot.json`](../data/matrix/coverage_snapshot.json) — **разбивка**, не «вся матрица executable».
6. [`data/dataset/tz_scorecard.json`](../data/dataset/tz_scorecard.json) — три контура Code / Acceptance / Production, без процента «по ТЗ».
7. [`WORK_PLAN.md`](WORK_PLAN.md), [`KNOWN_GAPS.md`](KNOWN_GAPS.md), [`PR_QUEUE.md`](PR_QUEUE.md), [`RESEARCH_OSINT_2026.md`](RESEARCH_OSINT_2026.md).
8. Issues [#75](https://github.com/KonkovDV/Kontur/issues/75)–[#84](https://github.com/KonkovDV/Kontur/issues/84), срез [#86](https://github.com/KonkovDV/Kontur/issues/86), эпик [#87](https://github.com/KonkovDV/Kontur/issues/87). Шина: [`GH_AGENT_BUS.md`](GH_AGENT_BUS.md).

Пересборка снимков: `python scripts/export_agent_dumps.py`.
`export_git_sha` в JSON может отставать на один docs-коммит — смотреть `git rev-parse HEAD`.

## Цифры (честные)

| Поле | Значение |
|---|---|
| Coverage declared | 132 |
| executable | **44** |
| extractor_missing | **83** |
| advisory | **1** |
| source_missing | **4** |
| executable доля | 25% — это coverage, не порог ТЗ |
| Публичный gold-позитив матрицы | 6 (нужно n≥16 даже при 6/6 для Wilson recall) |
| Gold-evidence прогон TRAIN_PUBLIC | 0/6: L4, у ПД F0171 нет заполненной графы «Утвердил» |
| Гейты I / J / K / L | все **открыты** (`closes_gate_*`: false) |
| OCR capabilities | `ocr_text=UNAVAILABLE` |
| HTTP пайплайн | L1–L7 inline после upload, векторный слой |
| РиН | транспорт outbox/inbox есть; sandbox-контракта и бизнес-ACK нет; confirm брокера ≠ `SYNCED` |

Семейства: number 24 executable / 64 missing; enum 5 / 11; exact_field 4 executable / 8 missing / 4 source_missing; presence 1 advisory / 11 missing.
Файл: [`data/matrix/extractor_families.json`](../data/matrix/extractor_families.json).

## Главный вывод на 21.09

Каркас доверенной системы сильный (human-only verdict, evidence, атомарный протокол,
outbox/inbox, fail-closed, claims-lint). **Транспорт обогнал конкурсное обнаружение
расхождений.** До 29.09 не наращивать production-инфру. Critical path:
PDF → эталон → evidence card → инспектор → протокол на пяти–восьми правилах.

Freeze: Prometheus/Grafana/ELK, OIDC/JWKS, TLS, backup/DR, УКЭП, РиН без контракта,
RabbitMQ 4.x, универсальный CV, VLM fine-tune, 132/132 экстракторов. Разрешены S0/S1.

## Что уже на `main` (не выдумывать заново)

- HTTP upload → токены → паспорт → `evaluate_rule` × 132 → `READY`; автомат не пишет `CONFIRMED_VIOLATION`
- Очередь READY→VERIFYING→COMPLETED; finalize только человек
- OCR fail-closed; region-crop dual-read в коде; SILVER не закрывает гейт I
- Эталон: штамп «Утвердил»+ФИО (ADR-0007). «Согласовано»/ГИП **не** approval
- Инспектор может назначить UNKNOWN эталоном: `POST /api/v1/processes/{id}/revisions/{file_id}/select` (комментарий обязателен). `NOT_APPROVED` нельзя перекрыть. Это не закрытие гейта J
- JWT RS256/ES256; публичен только `/healthz`; object scope; legacy dotted-токен только при `KONTUR_ALLOW_INSECURE_DEV_AUTH`
- Контейнеры UID 10001, read-only, cap_drop ALL, порты loopback (PR #60); лимиты mem/cpu/pids (PR #74)
- Postgres finalize fail-closed + versioned materialization (PR #64–65, ADR-0009). **Не** требовать `kind=materialized` / `assembled=true` в JSON ТЗ
- Outbox relay ADR-0010/0011; inbox ADR-0012; Compose `outbox-relay` + `inbox-consumer`
- Gate L k6 на GHA измерен (p95 `/status`); **не** production SLA
- Gate K: рекордер в `web/`; **сессий нет**
- `split()` = `NotImplementedError` (GAP-SPLIT)
- `main` без branch protection: GitHub Free private → API 403 ([#81](https://github.com/KonkovDV/Kontur/issues/81))

Влитые PR 21.09: #72 OpenAPI negatives, #73 inbox-consumer, inspector etalon `7ee5eed`, #74 compose limits.
Не вливать OCR: `16f3a06` (`feat/ocr-gate-i-crop3x-oem1`), `2ddc2b3` (`feat/ocr-300dpi-step2-verifying`).

Закрытые красным, не воскрешать: #61 monkeypatch ProcessRecord, #63 stripped provenance, #66 FK `objects.id=process_id` (исправлено на main).

## Чего нет в git (важно для GH-only агента)

Каталог `files/` в `.gitignore`. На машине разработчика 20.09.2026 наблюдалось
(см. `gold_inventory.json`), **в clone с GitHub этого нет**:

- `ПАКЕТ_УЧАСТНИКАМ_БЕЗ_ОТВЕТОВ_v2.0` (checksums 18/18)
- объект `10_Полярная_25_СОШ1100к7` (~20,9 ГБ) — не gold, не frozen val, не закрывает J
- `РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203`, карантин `РАЗМЕЧЕННЫЙ_TEST__213`
- закрытый zip организатора — **не открывать** для порогов, prompt, regex

Не угадывать не-gold `RD_ID_MIXED`. Overlay `annotated_documents` не источник скоринга.

## Backlog GitHub (делать это, не инфру)

| Issue | Тема |
|---|---|
| [#75](https://github.com/KonkovDV/Kontur/issues/75) | E2E PZ-001 / KR-055 / AR-041 / IOS4-078 / IOS4-079 |
| [#76](https://github.com/KonkovDV/Kontur/issues/76) | Двухпанельный evidence viewer |
| [#77](https://github.com/KonkovDV/Kontur/issues/77) | Gate K: пять сессий |
| [#78](https://github.com/KonkovDV/Kontur/issues/78) | Demo fixture + холодный Compose |
| [#79](https://github.com/KonkovDV/Kontur/issues/79) | Submission / evidence pack |
| [#80](https://github.com/KonkovDV/Kontur/issues/80) | Adversarial PDF + prompt injection |
| [#81](https://github.com/KonkovDV/Kontur/issues/81) | Branch protection (нужен Pro или public) |
| [#82](https://github.com/KonkovDV/Kontur/issues/82) | Family extractors exact_field / presence |
| [#83](https://github.com/KonkovDV/Kontur/issues/83) | GAP-SPLIT |
| [#84](https://github.com/KonkovDV/Kontur/issues/84) | Изоляция VLM от write/tools |
| [#86](https://github.com/KonkovDV/Kontur/issues/86) | Срез ситуации (читать первым) |
| [#87](https://github.com/KonkovDV/Kontur/issues/87) | Эпик вертикального среза; дети 75–80 |

## Запреты (коротко)

Автомат/LLM не пишут `CONFIRMED_VIOLATION`. Overlay нормы не меняет вердикт матрицы (ADR-0006).
`AUTO_NO_DIFFERENCE` не на проводе ТЗ. TEST_HIDDEN не открывать. Не закрывать I/J по SILVER, n=6, n=15.
Не публиковать метрики раздела 14 без frozen val, размера выборки и 95% CI
(порог приёмки не измерен). Confirm брокера / inbox RECEIVED ≠ `SYNCED` / Rin ACK.
Не считать инспекторский SELECT_REVISION доказательством штампа.

## Команды

```text
python -m pytest backend/tests -q
python scripts/check_claims.py
python scripts/check_contracts.py
python scripts/export_agent_dumps.py
```

Windows: нет `make`; `python -m kontur.evaluation.train_public` при наличии локальных PDF.
JWT для тестов: `KONTUR_ALLOW_INSECURE_DEV_AUTH` в `backend/tests/conftest.py`.
