"""Миграции поверх schema.sql: текст берётся из schema.sql, всё идемпотентно."""

from __future__ import annotations

from kontur.infrastructure.db.migrations import SCHEMA_PATH, migration_statements


def test_migration_reuses_guard_from_schema() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    add, function, drop, trigger, evidence, *files = migration_statements()
    assert add == "ALTER TABLE protocols ADD COLUMN IF NOT EXISTS full_payload JSONB"
    assert function.startswith("CREATE OR REPLACE FUNCTION protocols_guard_finalized()")
    assert function.replace("CREATE OR REPLACE FUNCTION", "CREATE FUNCTION", 1) in schema
    assert "NEW.full_payload" in function and "OLD.full_payload" in function
    assert drop == "DROP TRIGGER IF EXISTS protocols_finalized_is_immutable ON protocols"
    assert trigger in schema and trigger.startswith("CREATE TRIGGER")
    assert evidence.startswith("CREATE TABLE IF NOT EXISTS process_evidence_groups (")
    assert evidence.replace(" IF NOT EXISTS", "", 1) in schema
    assert files == [
        "ALTER TABLE process_files ADD COLUMN IF NOT EXISTS predecessor_file_id TEXT",
        "ALTER TABLE process_files ADD COLUMN IF NOT EXISTS successor_file_id TEXT",
        "ALTER TABLE process_files ADD COLUMN IF NOT EXISTS file_path TEXT",
    ]


class _Recorder:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.in_transaction = False

    def transaction(self) -> _Recorder:
        return self

    def __enter__(self) -> None:
        self.in_transaction = True

    def __exit__(self, *exc: object) -> None:
        self.in_transaction = False

    def execute(self, sql: str, params: object = None) -> _Recorder:
        assert self.in_transaction, sql
        self.sql.append(sql)
        return self

    def fetchone(self) -> tuple[bool]:
        return (True,)


def test_apply_runs_everything_inside_one_transaction_under_lock() -> None:
    from kontur.infrastructure.db.migrations import apply_migrations

    recorder = _Recorder()
    apply_migrations(recorder)
    assert recorder.sql[0].startswith("SELECT pg_advisory_xact_lock")
    assert recorder.sql[2:] == list(migration_statements())
