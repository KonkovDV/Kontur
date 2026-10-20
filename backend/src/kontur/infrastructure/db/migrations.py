"""Дополнительные миграции поверх schema.sql для уже развёрнутых баз.

schema.sql применяется один раз (docker-entrypoint-initdb.d, psql в CI). База,
созданная раньше, новых колонок не получит. Ядро с KONTUR_DB_URL вызывает
`apply_migrations` перед первым запросом к базе (ConnectingPostgresProcessStore).
Всё идемпотентно, в одной транзакции и под advisory-локом: несколько процессов,
стартуя одновременно, не мешают друг другу.

Текст триггерной функции берётся из schema.sql, второй копии нет.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
#: Ключ pg_advisory_xact_lock: «KNTM» в ASCII.
MIGRATION_LOCK_KEY = 0x4B4E544D

_GUARD_FUNCTION = re.compile(
    r"^CREATE FUNCTION protocols_guard_finalized\(\).*?^\$\$;$", re.MULTILINE | re.DOTALL
)
_EVIDENCE_TABLE = re.compile(
    r"^CREATE TABLE process_evidence_groups \(.*?^\);$", re.MULTILINE | re.DOTALL
)
_GUARD_TRIGGER = re.compile(
    r"^CREATE TRIGGER protocols_finalized_is_immutable\b.*?;$", re.MULTILINE | re.DOTALL
)


def _schema_block(pattern: re.Pattern[str], schema: str) -> str:
    match = pattern.search(schema)
    if match is None:
        raise RuntimeError(f"в schema.sql нет блока {pattern.pattern[:60]!r}")
    return match.group(0)


def migration_statements(schema: str | None = None) -> tuple[str, ...]:
    """0001: protocols.full_payload и триггер неизменности, который её сравнивает.

    0002: таблица process_evidence_groups (группы доказательств процесса).
    """

    text = SCHEMA_PATH.read_text(encoding="utf-8") if schema is None else schema
    function = _schema_block(_GUARD_FUNCTION, text).replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
    )
    trigger = _schema_block(_GUARD_TRIGGER, text)
    return (
        "ALTER TABLE protocols ADD COLUMN IF NOT EXISTS full_payload JSONB",
        function,
        "DROP TRIGGER IF EXISTS protocols_finalized_is_immutable ON protocols",
        trigger,
        _schema_block(_EVIDENCE_TABLE, text).replace(
            "CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1
        ),
        "ALTER TABLE process_files ADD COLUMN IF NOT EXISTS predecessor_file_id TEXT",
        "ALTER TABLE process_files ADD COLUMN IF NOT EXISTS successor_file_id TEXT",
        "ALTER TABLE process_files ADD COLUMN IF NOT EXISTS file_path TEXT",
    )


def apply_migrations(connection: object) -> None:
    """Применить миграции в одной транзакции. Повторный вызов ничего не меняет."""

    with connection.transaction():  # type: ignore[attr-defined]
        connection.execute(  # type: ignore[attr-defined]
            "SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,)
        )
        exists = connection.execute(  # type: ignore[attr-defined]
            "SELECT to_regclass('protocols') IS NOT NULL"
        ).fetchone()
        if not exists or not exists[0]:
            raise RuntimeError(
                "в базе нет таблицы protocols: сначала примените schema.sql"
            )
        for statement in migration_statements():
            connection.execute(statement)  # type: ignore[attr-defined]


def apply_migrations_dsn(dsn: str) -> None:
    import psycopg  # type: ignore[import-not-found,import-untyped,unused-ignore]

    with psycopg.connect(dsn) as connection:
        apply_migrations(connection)


def main(argv: list[str] | None = None) -> int:
    import os

    args = sys.argv[1:] if argv is None else argv
    dsn = args[0] if args else (os.environ.get("KONTUR_DB_URL") or "").strip()
    if not dsn:
        print("нужен KONTUR_DB_URL или DSN аргументом", file=sys.stderr)
        return 2
    apply_migrations_dsn(dsn)
    print("migrations: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
