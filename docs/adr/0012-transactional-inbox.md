# ADR-0012: transactional inbox, ACK after commit

**Статус:** предложено 20.09.2026.

## Контекст

Outbox публикует в RabbitMQ at-least-once (ADR-0010). Publisher confirm и
строка `integration_outbox.DELIVERED` означают только приём брокером.
Повторная доставка с тем же `event_id` обязательна; без inbox эффект
обработки будет повторён. RabbitMQ требует manual consumer ACK и готовности
к redelivery. `SYNCED` по-прежнему зарезервирован за бизнес-ACK РиН
(ADR-0011) и этим срезом не выставляется.

## Решение

1. Таблица `integration_inbox` с первичным ключом `event_id` (тот же
   стабильный `rin-{protocol_id}`).
2. Вставка `RECEIVED` или `POISON` в той же PostgreSQL-транзакции, что и
   побочный эффект consumer. `ON CONFLICT DO NOTHING` — exactly-once
   **effect**, не exactly-once transport.
3. Consumer ACK — только после `commit`. Сбой до commit оставляет сообщение
   unacked; повтор попадёт в уникальный ключ.
4. Prefetch = 1. После 4 неуспешных разборов: `POISON` + nack `requeue=false`
   в DLX `kontur.rin.dlx` / очередь `kontur.rin.protocol.poison`.
   У quorum-очереди `x-delivery-limit = 4`.
5. Inbox не пишет `processes.sync_state`. Состояния внешнего HTTP
   `submitted / confirmed / ambiguous` и reconciliation неизвестного
   результата РиН — следующий срез.

## Граница

Это не sandbox ИАИС, не УКЭП и не exactly-once на брокере. Если локальный
volume RabbitMQ уже держит `kontur.rin.protocol` без DLX-аргументов,
очередь нужно удалить, иначе `PRECONDITION_FAILED`.
