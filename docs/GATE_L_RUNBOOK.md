# Gate L: live k6 runbook

Gate L закрывается только живым прогоном API: 100 виртуальных пользователей,
60 секунд, polling `GET /status` после реального `POST /upload` и выполнения
пайплайна. Текстовый контракт скрипта сам по себе метрикой не является.

## Автоматический прогон

Workflow `.github/workflows/gate-l.yml`:

1. устанавливает backend из текущего commit;
2. запускает Uvicorn и ждёт `/healthz`;
3. `setup()` k6 загружает PDF и получает `process_id`;
4. 100 VU опрашивают status раз в секунду 60 секунд;
5. k6 применяет пороги `p(95)<200 ms` и error rate `<1%` только к тегу
   `name=status`, без setup-upload;
6. `render_k6_summary.py` проверяет наличие tagged-метрик и пишет JSON и
   Markdown с SHA, стендом, n, p50, p95, p99 и error rate;
7. raw summary, отчёт и лог API сохраняются artifact на 30 дней.

## Evidence

Скачать artifact `gate-l-<git-sha>` из workflow run. Минимальный набор:

- `k6-summary.json` — сырой результат;
- `gate-l-report.json` — нормализованный машинный отчёт;
- `gate-l-report.md` — строка для `docs/PERFORMANCE.md`;
- `api.log` — диагностика сервера.

Успешный check доказывает прохождение порогов на указанном GitHub-hosted
runner, но не переносит результат на production. Для итогового конкурсного
замера повторить workflow на зафиксированном стенде и перенести точные числа
из отчёта в `PERFORMANCE.md`.

## Stop conditions

- нет `process_id` после upload;
- status-метрика отсутствует или смешана с upload;
- p95 равен или превышает 200 мс;
- error rate равен или превышает 1%;
- отсутствуют p50/p95/p99, n, SHA или описание стенда;
- нагрузка выполнялась на пустом `PARSING` вместо процесса после пайплайна.
