# Ежедневная проверка SHA-256 хранилища (§13 п.8)

Сверка **реестр `file_hash` (`process_files`) ↔ тело в ObjectStore**. Не путать с `payload_sha256` outbox/RiN и с JSON-логами (§13 п.1).

## Команда

```bash
python -m kontur.cli.check_storage_integrity      # в образе core
PYTHONPATH=backend/src python scripts/check_storage_integrity.py   # с хоста (обёртка)
```

Реестр: `KONTUR_DB_URL` → Postgres `process_files` (`list_all_files()`), иначе in-memory (только smoke).
Тела: object store по тем же env, что у API.

| Exit | Смысл |
|---|---|
| 0 | все файлы совпали |
| 1 | любой файл: `mismatch` / `missing` / `no_hash` (пустой hash) / `invalid_hash` (не 64 hex) / `error` (сбой чтения по файлу) → ERROR + audit `STORAGE_INTEGRITY_MISMATCH` в `audit_log` |
| 3 | реестр пуст (0 файлов) — fail-closed; `KONTUR_INTEGRITY_ALLOW_EMPTY=1` для осознанного пропуска |
| 4 | `KONTUR_DB_URL` без object store — тела недоступны |
| 5 | реестр/хранилище недоступны (исключение) |

## Поведение прогона

- **Память:** sha256 считается потоково (чанки 1 МиБ; `iter_chunks` у Memory/S3 хранилищ), тело целиком в RAM не грузится. Реестр читается целиком одним запросом (кортежи `process_id, file_id, hash`) — для очень больших реестров нужна пагинация (не сделана).
- **Ошибки по файлу:** сбой S3/чтения или audit по одному файлу не прерывает прогон: файл получает статус `error` (сбой audit логируется), остальные проверяются, итог — все находки и exit 1. Exit 5 только если не удалось прочитать сам реестр.
- **Audit без флуда:** запись `STORAGE_INTEGRITY_MISMATCH` не повторяется, если для этого процесса уже есть событие с теми же `file_id`, `status`, `expected_hash`, `actual_hash`. Повреждённый файл даёт 1 запись, пока его состояние не изменилось (смена `actual_hash`/`status` — новая запись). Если прочитать прошлый audit не удалось — пишем (лучше дубль, чем пропуск). Каждый прогон при этом всё равно логирует ERROR и возвращает exit 1.

## Расписание

Compose-сервис `storage-integrity` (profile `integrity`, **opt-in**, не поднимается по умолчанию):

```bash
docker compose --profile integrity up -d storage-integrity
```

Цикл `прогон → sleep KONTUR_INTEGRITY_INTERVAL_S (по умолчанию 86400)`; код последнего прогона — в `/tmp/integrity.last`.

Healthcheck (интервал 60 с) различает состояния; текст виден в `docker inspect --format '{{json .State.Health}}' <container>`:

| Состояние | Файл `/tmp/integrity.last` | Вывод healthcheck | Статус контейнера |
|---|---|---|---|
| ещё не запускался / первый прогон идёт | нет | `not_yet_run` | `starting` в пределах `start_period` (`KONTUR_INTEGRITY_START_PERIOD`, по умолчанию 30m); если первый прогон дольше — `unhealthy` |
| последний прогон успешен | `0` | — | `healthy` |
| последний прогон неуспешен | `1`/`3`/`4`/`5` | `failed rc=N` | `unhealthy` (после `start_period`; сбой первого прогона внутри `start_period` ещё не меняет статус — смотрите логи) |

Это не доставка алертов (§13 п.7): состояние надо опрашивать/мониторить снаружи.

Альтернатива — cron на хосте (исполняемый пример, путь `/opt/kontur` — поправьте под стенд):

```cron
0 3 * * * cd /opt/kontur && docker compose --profile integrity run --rm --no-deps --entrypoint python storage-integrity -m kontur.cli.check_storage_integrity
```

(`--no-deps` предполагает, что postgres и minio уже подняты; код возврата `run` = exit-код проверки.)

## Чем проверено

- Unit (`backend/tests/test_storage_integrity.py`): совпадение, подмена байта, missing, пустой/не-hex/uppercase hash, 0 файлов, DB без object store, недоступный реестр, сбой чтения и сбой audit по одному файлу, дедуп audit, потоковый hash >1 МиБ, SQL/маппинг `list_all_files` на фейк-соединении.
- Live Postgres: `scripts/check_integrity_pg_live.py` — шаг workflow `sync-lifecycle-db` (реальный PG 16 + `schema.sql`): список файлов, byte-flip → exit 1 + строка в `audit_log`, пустой hash → exit 1, 0 файлов → exit 3. **Локально без Postgres не запускался**; доказательство — зелёный CI.

## Статус: partial

Не проверено/не сделано: прогон против реального MinIO/S3 (в тестах `MemoryObjectStore`), запуск compose-сервиса в CI (проверяется только `docker compose config`), доставка алертов (§13 п.7), потоковое чтение `S3ObjectStore.iter_chunks` (в тестах только Memory), нагрузка на большой реестр (полный обход без пагинации), поведение healthcheck в живом контейнере (shell-фрагмент проверен только вручную на 3 состояниях). §13 п.8 **не объявляется закрытым**.
