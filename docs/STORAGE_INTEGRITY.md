# Ежедневная проверка SHA-256 хранилища (§13 п.8)

Сверка **реестр `file_hash` ↔ тело в ObjectStore**. Не путать с `payload_sha256` outbox/RiN и с JSON-логами (§13 п.1).

## Команда

```bash
PYTHONPATH=backend/src python scripts/check_storage_integrity.py
```

- `ok=N bad=0` → exit 0
- любое `mismatch` / `missing` / `no_hash` (пустой file_hash в реестре) → ERROR в лог, audit `STORAGE_INTEGRITY_MISMATCH` (CLI передаёт audit-sink в MemoryProcessStore), exit 1
- реестр пуст (0 файлов) → exit 3 (fail-closed), кроме `KONTUR_INTEGRITY_ALLOW_EMPTY=1`
- Postgres list-all process_files в S-пакете ещё не wired: без `MemoryProcessStore` CLI возвращает exit 2 (не silent-ok), кроме `KONTUR_INTEGRITY_ALLOW_EMPTY_PG=1` для отладки

## Расписание (стенд)

Ежедневно (cron / systemd timer / CI schedule), например:

`0 3 * * * cd /opt/kontur && PYTHONPATH=backend/src python scripts/check_storage_integrity.py`

**Расписания в compose/timer в репозитории НЕТ** — выше только пример cron. Compose oneshot / timer — follow-up.

## Статус: partial

Логика + unit-тесты есть (in-memory). Postgres `list_all_files()` не реализован → на PG CLI exit 2; audit в PG-пути и расписание — follow-up. §13 п.8 **не закрыт**.

## Тест

`backend/tests/test_storage_integrity.py` — совпадение, подмена байта, отсутствующий blob.
