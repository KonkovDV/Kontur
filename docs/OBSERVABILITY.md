# Observability (§13 п.4–7) — честный срез

## Есть (partial)

| Что | Где |
|---|---|
| Prometheus exposition gateway | `GET :3000/metrics`, **Bearer `KONTUR_METRICS_TOKEN`**; без токена 403 (кроме `KONTUR_METRICS_ALLOW_ANON=1`) (`kontur_gateway_*`, `http_requests_total`, latency histogram) |
| Prometheus exposition core | `GET :8000/metrics` (process_* + `kontur_uploads_total` (findings/processing-метрики не реализованы — deferred)) |
| RabbitMQ queue metrics | плагин `rabbitmq_prometheus`, порт `127.0.0.1:15692` (`rabbitmq_queue_messages_ready`) |

`/metrics` **не** под `/api/v1` — наружу через gateway `/api/v1/*` не утекает.

Label `route`: только известные шаблоны `/api/v1/*` (id -> `:id`) и `/`, `/healthz`, `/metrics`; всё остальное -> `unmatched` (список `KNOWN_ROUTES` в `gateway/src/metrics.js` ручной — при добавлении эндпоинта ядра обновлять). Это не FastAPI/Express route template, а allowlist.

Backlog outbox и `kontur_findings_total` / `kontur_processing_seconds` — **не реализованы**.

## Нет до 30.10+ (deferred)

- Grafana dashboard / compose profile `observability` (опционально позже)
- ELK (§13 п.6)
- Доставка алертов email/Telegram (§13 п.7)
- «Активные сессии» (JWT stateless — не называем proxy gauge сессиями)
- Таблица `Monitoring_Metrics` в БД (роль TSDB у Prometheus)

Scorecard `observability_otel` = **partial**, не `met`.
