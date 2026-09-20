"""Ограничения GOLD: много меток на объект, объект целиком в одном split."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_DIR = (
    Path(__file__).resolve().parents[2] / "backend" / "src" / "kontur" / "infrastructure" / "db"
)
SCHEMA = DB_DIR / "schema.sql"
CHECKS = DB_DIR / "checks.sql"


def test_schema_sql_separates_object_split_from_gold_rows() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    assert "CREATE TABLE object_splits" in sql
    assert "UNIQUE (evidence_group_id, dataset_version)" in sql
    assert "dataset_items_object_split" not in sql
    assert "negative_requires_human" in sql
    assert "checks_object_status" in sql
    assert "files_object_stage" in sql
    assert "audit_log_object_ts" in sql


def test_two_gold_labels_same_object_live_but_two_splits_do_not() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE objects (id TEXT PRIMARY KEY);
        CREATE TABLE evidence_groups (id TEXT PRIMARY KEY);
        CREATE TABLE object_splits (
            object_id TEXT NOT NULL REFERENCES objects (id),
            dataset_version TEXT NOT NULL,
            split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
            PRIMARY KEY (object_id, dataset_version)
        );
        CREATE TABLE dataset_items (
            id TEXT PRIMARY KEY,
            evidence_group_id TEXT NOT NULL REFERENCES evidence_groups (id),
            dataset_version TEXT NOT NULL,
            object_id TEXT NOT NULL REFERENCES objects (id),
            FOREIGN KEY (object_id, dataset_version)
                REFERENCES object_splits (object_id, dataset_version),
            UNIQUE (evidence_group_id, dataset_version)
        );
        """
    )
    conn.execute("INSERT INTO objects VALUES ('obj-10')")
    conn.execute("INSERT INTO evidence_groups VALUES ('eg-a')")
    conn.execute("INSERT INTO evidence_groups VALUES ('eg-b')")
    conn.execute("INSERT INTO object_splits VALUES ('obj-10', 'v1', 'train')")
    conn.execute("INSERT INTO dataset_items VALUES ('row-1', 'eg-a', 'v1', 'obj-10')")
    conn.execute("INSERT INTO dataset_items VALUES ('row-2', 'eg-b', 'v1', 'obj-10')")

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO object_splits VALUES ('obj-10', 'v1', 'validation')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dataset_items VALUES ('row-3', 'eg-a', 'v1', 'obj-10')")
    conn.close()


def test_schema_freezes_process_state_and_finalization_invariants() -> None:
    """Postgres-ограничения нельзя выполнить в sqlite, но их исчезновение видно здесь."""

    sql = SCHEMA.read_text(encoding="utf-8")
    assert "CREATE TABLE processes" in sql
    assert "completeness_pd" in sql
    assert "CREATE TABLE process_findings" in sql
    assert "CREATE TABLE process_files" in sql
    assert "process_violation_requires_human" in sql
    assert "audit_log_process_ts" in sql
    assert "processes_object_state" in sql
    assert "parse_attempts BETWEEN 0 AND 3" in sql
    assert "sync_attempts BETWEEN 0 AND 4" in sql
    assert "finalized_needs_human" in sql
    assert "sync_only_after_finalize" in sql
    assert "protocols_finalized_is_immutable" in sql
    assert "kontur.unfinalize_reason" in sql
    assert "KNT01" in sql
    assert "не может менять содержимое" in sql
    assert "KNT02" in sql
    assert "processes_sync_requires_finalized_protocol" in sql
    assert "AUTO_NO_DIFFERENCE', 'SUSPICION'" in sql
    assert "gold_label IN ('CONFIRMED_VIOLATION', 'NEGATIVE_VERIFIED')" in sql
    assert "gold_requires_expert" in sql
    assert "negative_gold_requires_reason" in sql
    assert "UNIQUE (object_id, version)" in sql
    assert "payload_sha256" in sql
    assert "CREATE TABLE integration_inbox" in sql
    assert "CREATE TABLE integration_outbox" in sql
    assert "event_id" in sql
    assert "available_at" in sql
    assert "FOR UPDATE SKIP LOCKED" not in sql


def test_schema_sync_guard_rejects_placeholder_and_false_assembled() -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    assert "payload ->> 'kind'" in sql
    assert "proto_kind = 'internal_placeholder'" in sql
    assert "payload -> 'assembled'" in sql
    assert "proto_assembled = 'false'::jsonb" in sql
    assert "proto_assembled IS NULL" not in sql
    assert "payload_sha256" in sql
    assert "btrim(proto_sha)" in sql
    assert "IS DISTINCT FROM 'materialized'" not in sql


def test_checks_sql_allows_tz_payload_without_kind_or_assembled() -> None:
    checks = CHECKS.read_text(encoding="utf-8")
    assert "proto-no-assembled-check" in checks
    assert '"protocol_id":"proto-no-assembled-check"' in checks
    assert "rin-proto-check" in checks
    assert "inbox принял SYNCED" in checks
    assert '\'{"kind":"materialized"}\'::jsonb' not in checks
    assert "IS DISTINCT FROM 'materialized'" not in checks


def test_checks_sql_asserts_instead_of_merely_running() -> None:
    """checks.sql обязан ловить отсутствие ограничения, а не любую ошибку подряд."""

    checks = CHECKS.read_text(encoding="utf-8")
    assert checks.count("DO $$") >= 15
    assert "process_findings" in checks
    assert "process_files" in checks
    assert checks.count("DO $$") == checks.count("END;\n$$;")
    assert "KNT99" in checks
    assert "KNT02" in checks
    assert "SQLSTATE 'KNT01'" in checks
    assert "WHEN SQLSTATE 'KNT02' THEN NULL;" in checks
    assert "отмена финализации изменила содержимое" in checks
    assert "WHEN check_violation THEN NULL;" in checks
    assert checks.rstrip().endswith("ROLLBACK;")


def test_machine_status_cannot_become_a_gold_label() -> None:
    """ТЗ п. 9.4: разметка — только человеческий вердикт, и только с экспертом."""

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE dataset_items (
            id TEXT PRIMARY KEY,
            gold_label TEXT
                CHECK (gold_label IN ('CONFIRMED_VIOLATION', 'NEGATIVE_VERIFIED')),
            expert_id TEXT,
            reason_code TEXT,
            CONSTRAINT gold_requires_expert CHECK (
                gold_label IS NULL
                OR (expert_id IS NOT NULL AND trim(expert_id) <> '')
            ),
            CONSTRAINT negative_gold_requires_reason CHECK (
                gold_label IS NULL
                OR gold_label <> 'NEGATIVE_VERIFIED'
                OR (reason_code IS NOT NULL AND trim(reason_code) <> '')
            )
        );
        """
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dataset_items VALUES ('a', 'AUTO_NO_DIFFERENCE', 'exp', NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dataset_items VALUES ('b', 'CONFIRMED_VIOLATION', '  ', NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO dataset_items VALUES ('c', 'NEGATIVE_VERIFIED', 'exp', NULL)")
    conn.execute("INSERT INTO dataset_items VALUES ('d', 'CONFIRMED_VIOLATION', 'exp', NULL)")
    conn.execute("INSERT INTO dataset_items VALUES ('e', 'NEGATIVE_VERIFIED', 'exp', 'OCR_ERROR')")
    conn.close()
