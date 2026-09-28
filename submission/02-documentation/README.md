# Документация

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/02-documentation

Гейты I/J/K/L открыты. Покрытие — 55 executable, 72 extractor_missing,
1 advisory, 4 source_missing из 132. Это не заявление, что все параметры исполняются.

## За пять минут

1. [`README.md`](../../README.md) — команда запуска и список «работает / не работает».
2. [`ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) — три контура и где вердикт.
3. [`METRICS.md`](../../docs/METRICS.md) — пороги раздела 14 как пороги приёмки.
4. [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md) — что не сделано.
5. Этот пакет — [`submission/README.md`](../README.md).

## Что просит ответ О-2

| Требование | Где в репозитории |
|---|---|
| Репозиторий | https://github.com/KonkovDV/Kontur |
| Dockerfile | [`backend/Dockerfile`](../../backend/Dockerfile), [`backend/Dockerfile.relay`](../../backend/Dockerfile.relay), [`gateway/Dockerfile`](../../gateway/Dockerfile) |
| Compose | [`docker-compose.yml`](../../docker-compose.yml), [`docker-compose.demo.yml`](../../docker-compose.demo.yml), [`docker-compose.offline.yml`](../../docker-compose.offline.yml) |
| Lock | [`backend/requirements.lock`](../../backend/requirements.lock), [`web/package-lock.json`](../../web/package-lock.json), [`gateway/package-lock.json`](../../gateway/package-lock.json) |
| Локальные веса | [`vendor/ocr/`](../../vendor/ocr/), [`ocr_weights.lock.json`](../../backend/src/kontur/infrastructure/ocr_weights.lock.json) |
| Команда запуска | [`README.md`](../../README.md) |
| Healthcheck | [`docker-compose.yml`](../../docker-compose.yml) |
| OpenAPI | [`openapi.yaml`](../../contracts/openapi.yaml) (3.1), [`openapi-3.0.yaml`](../../contracts/openapi-3.0.yaml) |
| Пример JSON | [`examples/`](../05-additional/examples/README.md) |

Публичная ссылка на стенд решением не оценивается. Внешние LLM, OCR и VLM
в зачётный прогон не входят.

## Где смотреть требования ТЗ

Построчная карта и её статусы — только в
[`TZ_TRACEABILITY.md`](../../docs/TZ_TRACEABILITY.md). Здесь статусы не повышаются.

| Блок | Куда идти |
|---|---|
| Контракт API и состав стенда | тот же файл, пункты 1.3–1.5 |
| Матрица и разделы документов | пункты 3–8 и приложение 1 |
| Разбор, сверка, карточка, каскад | пункт 9.1–9.2 |
| Решение инспектора и финализация | пункт 9.3 |
| Разметка, карантин, скрытый тест | пункт 9.4 |
| Подозрение вне 132 правил | пункт 9.5 |
| Очередь в РиН | пункт 9.6 |
| Хранение и доступ | пункты 10 и 12 |
| Пороги раздела 14 и формат ответа | пункт 14 и приложение 2 |

## Решения

| ADR | О чём |
|---|---|
| [0001](../../docs/adr/0001-llm-never-sets-verdict.md) | Модель не пишет вердикт |
| [0002](../../docs/adr/0002-evidence-group-is-the-unit.md) | Единица результата — evidence_group |
| [0003](../../docs/adr/0003-revision-resolver-before-comparison.md) | Редакция выбирается до сравнения |
| [0004](../../docs/adr/0004-rules-are-data.md) | 132 параметра — данные |
| [0005](../../docs/adr/0005-status-domains-are-separate.md) | Домены статусов разделены |
| [0006](../../docs/adr/0006-compare-documents-not-norms.md) | Сверка ПД↔РД↔ИД, не проект против нормы |
| [0007](../../docs/adr/0007-approval-requires-explicit-evidence.md) | Утверждение требует явного доказательства |
| [0008](../../docs/adr/0008-object-scope-is-mandatory.md) | На HTTP обязателен object scope |
| [0009](../../docs/adr/0009-atomic-protocol-materialization.md) | Протокол материализуется атомарно |
| [0010](../../docs/adr/0010-outbox-relay-to-broker.md) | Outbox доставляет брокеру, не РиН |
| [0011](../../docs/adr/0011-sync-lifecycle-and-manual-retry.md) | Жизненный цикл брокера не есть доставка в РиН |
| [0012](../../docs/adr/0012-transactional-inbox.md) | Inbox подтверждает доставку после commit |
| [0013](../../docs/adr/0013-approval-sources-pending-written-answer.md) | Новый источник утверждения ждёт письменный ответ |
| [0014](../../docs/adr/0014-package-default-etalon.md) | ПД комплекта — эталон, если нет явного отказа |
| [0015](../../docs/adr/0015-missing-approval-is-clarification.md) | Режим `strict`: нет сведений об утверждении — не эталон |
| [0016](../../docs/adr/0016-completeness-needs-a-register.md) | Полнота комплекта считается по реестру |
| [0017](../../docs/adr/0017-sole-head-without-stamp.md) | Умолчание: единственная голова ПД без штампа сравнивается с плашкой |

## Контракты

В [`contracts/schemas/`](../../contracts/schemas/) восемь JSON-схем и
[`protocol-export.xsd`](../../contracts/schemas/protocol-export.xsd):
[`finding`](../../contracts/schemas/finding.schema.json),
[`evidence_group`](../../contracts/schemas/evidence_group.schema.json),
[`evidence_card`](../../contracts/schemas/evidence_card.schema.json),
[`document_passport`](../../contracts/schemas/document_passport.schema.json),
[`rule`](../../contracts/schemas/rule.schema.json),
[`protocol`](../../contracts/schemas/protocol.schema.json),
[`submission`](../../contracts/schemas/submission.schema.json),
[`submission_pack`](../../contracts/schemas/submission_pack.schema.json).

## Инварианты

| Правило | Следствие |
|---|---|
| `CONFIRMED_VIOLATION` пишет только инспектор | Автомат останавливается на `CANDIDATE` |
| Нет документа стадии | Это не нарушение: `MISSING_EVIDENCE` или `NOT_APPLICABLE` |
| Предметная находка | Нужны `evidence_group_id`, SHA-256, страница и polygon |
| Покрытие | 55 / 72 / 1 / 4 из 132, не «все параметры исполняются» |
