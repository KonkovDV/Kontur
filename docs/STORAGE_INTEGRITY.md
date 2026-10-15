# Ежедневная проверка SHA-256 хранилища (§13 п.8)

Сверка **реестр `file_hash` ↔ тело в ObjectStore**. Не путать с `payload_sha256` outbox/RiN и с JSON-логами (§13 п.1).

## Команда

```bash
PYTHONPATH=backend/src python scripts/check_storage_integrity.py
```

- `ok=N bad=0` → exit 0
- любое `mismatch` / `missing` → ERROR в лог, опционально audit `STORAGE_INTEGRITY_MISMATCH`, exit 1
- Postgres list-all process_files в S-пакете ещё не wired: без `MemoryProcessStore` CLI возвращает exit 2 (не silent-ok), кроме `KONTUR_INTEGRITY_ALLOW_EMPTY_PG=1` для отладки

## Расписание (стенд)

Ежедневно (cron / systemd timer / CI schedule), например:

`0 3 * * * cd /opt/kontur && PYTHONPATH=backend/src python scripts/check_storage_integrity.py`

Compose oneshot-сервис — опционально после зелёных unit-тестов; не блокер закрытия §13 п.8 тестом.

## Тест

`backend/tests/test_storage_integrity.py` — совпадение, подмена байта, отсутствующий blob.
