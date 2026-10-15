#!/usr/bin/env python3
"""§13 п.8: ежедневная проверка SHA-256 хранилища vs реестр file_hash.

Контракт для cron/CI (стенд):

  PYTHONPATH=backend/src python scripts/check_storage_integrity.py

По умолчанию — in-memory; 0 файлов → exit 3 (fail-closed). Для реального стенда задайте
``KONTUR_DB_URL`` + object store env (как API) — тогда обход идёт через
workspace wiring. Расхождение → ERROR в лог, exit 1.

Не путать с ``payload_sha256`` outbox/RiN.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from kontur.application.wiring import build_object_store, build_process_store  # noqa: E402
from kontur.infrastructure.db.process_store import MemoryProcessStore  # noqa: E402
from kontur.infrastructure.storage_integrity import (  # noqa: E402
    check_storage_integrity,
    registry_from_memory,
)


def main() -> int:
    store = build_process_store()
    objects = build_object_store()
    if not isinstance(store, MemoryProcessStore):
        print(
            "check_storage_integrity: Postgres list-all process_files ещё не "
            "в S-пакете; передайте MemoryProcessStore или дождитесь PG wiring.",
            file=sys.stderr,
        )
        # Честный S: CLI контракт есть; PG list — follow-up. Не silent-ok на PG.
        if os.environ.get("KONTUR_INTEGRITY_ALLOW_EMPTY_PG") == "1":
            print("ok=0 bad=0 (empty allow)")
            return 0
        return 2

    entries = registry_from_memory(store)
    if not entries and os.environ.get("KONTUR_INTEGRITY_ALLOW_EMPTY") != "1":
        # Вакуумный pass недопустим для cron: 0 файлов = нечего проверять.
        print(
            "check_storage_integrity: реестр пуст (0 файлов) — fail-closed; "
            "KONTUR_INTEGRITY_ALLOW_EMPTY=1 для осознанного пропуска.",
            file=sys.stderr,
        )
        return 3

    def _audit(actor: str, action: str, payload: dict[str, object]) -> None:
        store.save_audit_event(str(payload["process_id"]), actor, action, payload)

    report = check_storage_integrity(entries, objects, audit=_audit)
    print(f"ok={report.ok} bad={report.bad}")
    for item in report.findings:
        if item.status == "ok":
            continue
        print(
            f"{item.status}\t{item.process_id}\t{item.file_id}\t"
            f"expected={item.expected_hash}\tactual={item.actual_hash or '-'}"
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
