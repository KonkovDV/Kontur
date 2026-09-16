"""Ограничения GOLD: много меток на объект, объект целиком в одном split."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "src"
    / "kontur"
    / "infrastructure"
    / "db"
    / "schema.sql"
)


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
