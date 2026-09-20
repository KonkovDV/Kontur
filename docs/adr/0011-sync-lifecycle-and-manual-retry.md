# ADR-0011: broker lifecycle is not Rin delivery

**Статус:** предложено 20.09.2026.

## Контекст

RabbitMQ подтверждает хранение сообщения в durable/quorum queue, но consumer и
РиН ещё не подтверждали бизнес-обработку. Официальная документация RabbitMQ
разделяет publisher confirms и consumer acknowledgements и прямо требует
готовности к redelivery/idempotence. Поэтому `DELIVERED` outbox нельзя отражать
как `process.sync_state = SYNCED`.

Политика приложения уже требует после трёх повторов 1/5/15 минут вернуть
протокол в `PENDING_SYNC` для ручной отправки и уведомить администратора. Старый
relay завершал только outbox как `FAILED_TERMINAL` и не проецировал состояние в
`processes`, что расходилось с этой политикой.

## Решение

1. Claim outbox атомарно переводит процесс в `SYNCING` и копирует номер попытки.
2. Nack/timeout переводит процесс в `RETRY_WAIT`; outbox ждёт 1/5/15 минут.
3. Publisher confirm оставляет процесс в `SYNCING`: это только broker accept.
4. После четвёртой неуспешной попытки outbox остаётся `FAILED_TERMINAL` как
   техническая защита от бесконечного цикла, но процесс возвращается в
   `PENDING_SYNC`; создаётся идемпотентное событие аудита
   `SYNC_RETRY_EXHAUSTED`.
5. Ручной retry требует непустой `actor_id`, сбрасывает attempts и возвращает
   outbox в `PENDING`; действие фиксируется как `SYNC_MANUAL_RETRY`.
6. Все изменения outbox/process/audit выполняются в одной PostgreSQL-транзакции.

## Граница

Это не inbox consumer, не бизнес-ACK РиН и не exactly-once. Следующий срез должен
обрабатывать stable `event_id` с manual consumer ACK и атомарной inbox-записью;
при неизвестном результате внешнего HTTP требуется reconciliation, а не
угадывание успеха.
