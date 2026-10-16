"""Живой PostgreSQL: группы доказательств переживают рестарт ядра.

Временная база со schema.sql, учебный комплект через рабочий store ядра, выбор
эталона, затем новый ProcessWorkspace на той же базе (как после рестарта):
группы те же, места находок не пустые.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from kontur.application.runtime import ProcessWorkspace  # noqa: E402
from kontur.domain.state_machines import Actor  # noqa: E402
from kontur.evaluation.demo_kit import (  # noqa: E402
    DEMO_OBJECT_ID,
    ETALON_FILE_ID,
    install_demo_kit,
)
from kontur.infrastructure.db.connecting_store import ConnectingPostgresProcessStore  # noqa: E402
from kontur.infrastructure.db.migrations import SCHEMA_PATH  # noqa: E402
from kontur.infrastructure.object_store import MemoryObjectStore  # noqa: E402

DSN = os.environ.get("KONTUR_DB_URL", "postgresql://postgres:postgres@localhost:5432/kontur")


def main() -> int:
    name = f"kontur_evid_{uuid4().hex[:12]}"
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    target = psycopg.conninfo.make_conninfo(DSN, dbname=name)
    try:
        with psycopg.connect(target, autocommit=True) as connection:
            connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO objects (id, name) VALUES (%s, %s)", (DEMO_OBJECT_ID, DEMO_OBJECT_ID)
            )
        objects = MemoryObjectStore()
        first = ProcessWorkspace(store=ConnectingPostgresProcessStore(target), objects=objects)
        record = install_demo_kit(first, DEMO_OBJECT_ID)
        selected = first.select_revision(
            record.process_id,
            ETALON_FILE_ID,
            actor=Actor(actor_id="insp", is_human=True),
            comment="Утверждённая редакция.",
        )
        if not selected.evidence_groups:
            raise SystemExit("FAIL: после выбора эталона нет групп доказательств")
        second = ProcessWorkspace(store=ConnectingPostgresProcessStore(target), objects=objects)
        restored = second.get(record.process_id)
        if restored is None:
            raise SystemExit("FAIL: процесс не читается после рестарта")
        if restored.evidence_groups != selected.evidence_groups:
            raise SystemExit("FAIL: группы доказательств после рестарта отличаются")
    finally:
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    print(f"evidence groups: {len(selected.evidence_groups)} survive a core restart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
