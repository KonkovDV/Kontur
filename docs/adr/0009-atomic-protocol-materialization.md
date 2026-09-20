# ADR-0009: атомарная versioned materialization протокола

**Статус:** принято 20.09.2026.

## Контекст

Финализация без неизменяемого снимка оставляла `FINALIZED` с placeholder
`protocol_id` или с JSON `kind=internal_placeholder`. Выгрузка в РиН тогда
могла опереться на несуществующий протокол ТЗ. PR #64 закрыл `save(FINALIZED)`
в PostgreSQL. Последующий срез пишет protocol + process + `integration_outbox`
в одной транзакции и считает SHA-256 канонического JSON.

`protocol.schema.json` имеет `additionalProperties: false`. Поля `kind` и
`assembled` **не входят** в провод ТЗ. Требовать
`payload->>'kind' = 'materialized'` как условие sync отклонило бы валидный
`assemble_protocol()` и сломало бы Приложение 2.

## Решение

1. Application собирает payload по схеме ТЗ. Infrastructure не импортирует
   `assemble_protocol`. Provenance находок (`source_id`, `evidence_refs`,
   `disagreement_kind`) не вырезается.
2. Граница fail-closed — типизированные колонки: `protocols.status`,
   `payload_sha256` (`CHAR(64)` hex), `UNIQUE (object_id, version)`,
   FK `processes.protocol_id`.
3. Guard выгрузки отклоняет `internal_placeholder`, JSON `assembled=false`
   (legacy) и протокол без hex SHA-256. Отсутствующий `assembled` **разрешён**:
   это штатный JSON ТЗ, не дыра.
4. Версия: `protocol-{process_id}` для v1, иначе `-vN`. Unfinalize не правит
   старую строку `PROTOCOL_FINALIZED`; повтор создаёт новую версию.
5. В транзакции: `pg_advisory_xact_lock(object_id)`, `FOR UPDATE` процесса,
   находок и протоколов объекта, INSERT protocol, UPSERT process, INSERT
   outbox `PENDING`. Нет `connection.transaction()` — отказ.
6. Изоляция `SERIALIZABLE` и живые 20 concurrent finalize — следующий срез,
   не замена текущих UNIQUE + lock.

## Последствия

JSON-флаг не security boundary. VLM не пишет `CONFIRMED_VIOLATION`
(ADR-0001). Outbox — постановка в очередь, не доставка в РиН и не УКЭП.
