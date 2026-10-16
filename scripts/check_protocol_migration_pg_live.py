"""Живой PostgreSQL: база со схемой до full_payload переживает старт нового ядра.

Создаёт отдельную временную базу, разворачивает в ней schema.sql без колонки
full_payload (как до миграции 0001), кладёт финализированный протокол, затем
дважды применяет миграции тем же вызовом, что делает ядро при старте.
Проверяет: старая строка читается, триггер неизменности по-прежнему запрещает
правку и удаление (в том числе новой колонки), повтор миграции ничего не ломает.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from kontur.infrastructure.db.migrations import (  # noqa: E402
    SCHEMA_PATH,
    apply_migrations,
    apply_migrations_dsn,
)
from kontur.infrastructure.db.process_store import PostgresProcessStore  # noqa: E402

DSN = os.environ.get("KONTUR_DB_URL", "postgresql://postgres:postgres@localhost:5432/kontur")


def schema_before_full_payload() -> str:
    """schema.sql в виде до миграции 0001: без full_payload в таблице и в триггере."""

    lines = [
        line
        for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines()
        if "full_payload" not in line or "NEW.full_payload" in line or "OLD.full_payload" in line
    ]
    old = "\n".join(lines).replace("NEW.full_payload, ", "").replace("OLD.full_payload, ", "")
    if "full_payload" in old:
        raise SystemExit("FAIL: не удалось получить схему до full_payload")
    return old


def _expect_refusal(connection: psycopg.Connection, sql: str, protocol_id: str) -> None:
    try:
        with connection.transaction():
            connection.execute(sql, {"id": protocol_id})
    except psycopg.Error as exc:
        if exc.sqlstate != "KNT01":
            raise SystemExit(f"FAIL: ожидался KNT01, получен {exc.sqlstate}: {exc}") from exc
        return
    raise SystemExit(f"FAIL: триггер пропустил {sql!r}")


def main() -> int:
    name = f"kontur_migr_{uuid4().hex[:12]}"
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    target = psycopg.conninfo.make_conninfo(DSN, dbname=name)
    try:
        payload = {"protocol_id": "P-OLD", "object_id": "OBJ-OLD", "version": 1}
        sha = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with psycopg.connect(target, autocommit=True) as connection:
            connection.execute(schema_before_full_payload())
            connection.execute("INSERT INTO objects (id, name) VALUES ('OBJ-OLD', 'OBJ-OLD')")
            connection.execute(
                "INSERT INTO protocols (id, object_id, version, matrix_version, dataset_version,"
                " model_version, input_manifest_hash, status, payload, payload_sha256,"
                " finalized_at) VALUES ('P-OLD', 'OBJ-OLD', 1, 'm', 'd', 'v', 'h',"
                " 'PROTOCOL_FINALIZED', %s, %s, now())",
                (json.dumps(payload), sha),
            )
            column = connection.execute(
                "SELECT 1 FROM information_schema.columns"
                " WHERE table_name = 'protocols' AND column_name = 'full_payload'"
            ).fetchone()
            if column is not None:
                raise SystemExit("FAIL: старая схема уже содержит full_payload")

        apply_migrations_dsn(target)  # старт ядра
        with psycopg.connect(target) as connection:
            apply_migrations(connection)  # повторный старт: идемпотентно
            store = PostgresProcessStore(connection)
            if store.load_protocol("P-OLD") != payload:
                raise SystemExit("FAIL: старый протокол не читается после миграции")
            if store.load_full_protocol("P-OLD") is not None:
                raise SystemExit("FAIL: у старой строки появился full_payload")
            connection.commit()
            _expect_refusal(
                connection, "UPDATE protocols SET full_payload = '{}' WHERE id = %(id)s", "P-OLD"
            )
            _expect_refusal(
                connection, "UPDATE protocols SET payload = '{}' WHERE id = %(id)s", "P-OLD"
            )
            _expect_refusal(connection, "DELETE FROM protocols WHERE id = %(id)s", "P-OLD")
            triggers = connection.execute(
                "SELECT count(*) FROM pg_trigger"
                " WHERE tgname = 'protocols_finalized_is_immutable' AND NOT tgisinternal"
            ).fetchone()
            if triggers is None or triggers[0] != 1:
                raise SystemExit(f"FAIL: триггеров неизменности {triggers}")
    finally:
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    print("protocol migration: old rows readable, immutability trigger enforced, idempotent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
