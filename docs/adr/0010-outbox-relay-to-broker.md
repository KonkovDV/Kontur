# ADR-0010: outbox relay to broker, not Rin

**Статус:** принято 20.09.2026.

## Контекст

Финализация атомарно ставит `integration_outbox` в `PENDING` (ADR-0009).
Это ещё не доставка в РиН. RabbitMQ даёт at-least-once; publisher confirm
подтверждает приём брокером, не обработку consumer и не ACK ИАИС.

## Решение

1. Relay забирает строку `FOR UPDATE SKIP LOCKED`, статус `DELIVERING`,
   короткий lease на `available_at`.
2. `event_id = rin-{protocol_id}` стабилен на всех повторах (`message_id`).
3. Публикация — durable quorum queue `kontur.rin.protocol`, publisher
   confirms, timeout, mandatory, persistent. Тело — канонический JSON;
   SHA-256 должен совпасть с колонкой. Классическую очередь с тем же
   именем не объявлять: при уже существующем classic volume удалить
   очередь или volume.
4. Nack/timeout: паузы 1, 5, 15 минут, затем `FAILED_TERMINAL`.
   Несовпадение SHA — сразу terminal.
5. HTTP по-прежнему гоняет L1–L7 inline. Inbox consumer и sandbox РиН —
   отдельные срезы. Worker — отдельный контейнер UID 10001. Compose
   использует пользователя `kontur`, не `guest` между контейнерами.

## Последствия

Можно честно сказать «сообщение принято брокером». Нельзя сказать
«доставлено в РиН» или «exactly-once».
