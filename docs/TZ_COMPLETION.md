# Программа доведения до ТЗ (честные границы)

Дедлайн подачи — 29.09.2026 23:59 МСК. Этот документ принимает трёхконтурную
модель из аудита и **отвергает** публикацию одной цифры готовности как порога
ТЗ. Scorecard: [`TZ_SCORECARD.md`](TZ_SCORECARD.md).

Инварианты — [`AGENTS.md`](../AGENTS.md). Overlay нормы не источник скоринга.
`CONFIRMED_VIOLATION` пишет только инспектор. TEST_HIDDEN не открывать.

## Что уже не в бэклоге P0

- PR #64 и #65 влиты в `main`: fail-closed Postgres `save(FINALIZED)`,
  versioned materialization, advisory lock, `FOR UPDATE`, `payload_sha256`,
  outbox PENDING, `protocol-{process_id}` / `-vN`. JSON `kind=materialized`
  в payload **нет** (ADR-0009): схема ТЗ `additionalProperties: false`.
- `ENSURE_OBJECT` пишет `objects.id = object_id`, не process_id. CI `db`
  гоняет идемпотентный retry, гонку version и outbox `SKIP LOCKED`.
- Outbox relay (ADR-0010 / PR #67): отдельный worker UID 10001, quorum
  `kontur.rin.protocol`, confirms, паузы 1/5/15 мин, стабильный `event_id`.
  PR #68 проецирует попытки в `processes.sync_state` без `SYNCED` от брокера.
  Inbox (ADR-0012 / #69/#71): unique `event_id`, persist затем await ack,
  prefetch 1, poison/DLX. Compose-сервис `inbox-consumer` UID 10001.
  Не РиН, HTTP всё ещё inline.
- OSINT-срез и bake-off кандидаты: [`RESEARCH_OSINT_2026.md`](RESEARCH_OSINT_2026.md).
  Это не bake-off на GOLD и не закрытие I/J.

## Что план аудита верно требует — и что кодом не закрыть

| Требование | Статус |
|---|---|
| Три независимых scorecard | ведётся JSON, без процента «по ТЗ» |
| 132/132 executable | 55 executable, 72 `extractor_missing`, 1 advisory, 4 source_missing |
| GOLD OCR / frozen val | нет; SILVER и n=6 не закрывают I/J |
| Пять инспекторов Gate K | рекордер есть; сессий нет |
| RabbitMQ + MinIO + outbox workers | relay+inbox контейнеры; HTTP inline; РиН ACK нет |
| OIDC/JWKS, TLS 1.3, AV, backup | не production |
| SOTA bake-off OCR/VLM | нужен собственный GOLD, не общий leaderboard |

Каскад «модель предлагает → движок сравнивает → инспектор решает» уже
зафиксирован ADR-0001. VLM не автор вердикта.

## Семейства экстракции

Не реализовывать оставшиеся `extractor_missing` по одному. Сначала кластер по уже
скомпилированному `extractor.type` (`number` / `enum` / `exact_field` /
`presence`). Файл [`extractor_families.json`](../data/matrix/extractor_families.json)
только группирует коды. Пока нет рабочего экстрактора и фикстур, coverage
остаётся `extractor_missing`.

Критические 106 не объявлять закрытыми без frozen val.

## Конкурсный RC (реалистично)

1. Безопасный PostgreSQL finalize (ADR-0009: колонки, не `kind=materialized`).
2. Gate K: пять сессий человеком; код рекордера не закрывает гейт.
3. Честный coverage 55 executable / 72 extractor_missing / 1 advisory / 4 source_missing; без заявления,
   что вся матрица executable.
4. E2E demo на векторном слое; `ocr_text=MEASURED`, гейт I открыт.
5. Gate L измерен на GHA и **не** назван production SLA.
6. Capabilities честно показывают пробелы.

## Порядок следующих слайсов

1. Вертикальный срез: эталон инспектором → evidence card → review → protocol
   на `PZ-001` / `KR-055` / `AR-041` / `IOS4-078` / `IOS4-079`.
2. Пять сессий Gate K → `USABILITY_RESULTS.md`.
3. Family-wise экстракторы (`exact_field` / `presence`) с fixtures, не по одному коду.
4. `split()` (GAP-SPLIT) до демо.
5. Prompt-injection fixtures в PDF; VLM без write/tools.
6. Независимый GOLD OCR и frozen val по `object_id` (поставка, не код).
7. Sandbox РиН / `submitted|confirmed|ambiguous` — после acceptance-среза.
8. OIDC/JWKS, TLS, AV, monitoring, backup — после подачи, не вместо неё.

Полноценный обзор моделей 2025–2026 (лицензия, VRAM, кириллица, grounding)
нужен только как **эксперимент на GOLD**, не как выбор «самой умной» модели
в компаратор.
