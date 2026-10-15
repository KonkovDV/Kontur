#!/usr/bin/env python3
"""§13 п.8: ежедневная проверка SHA-256 хранилища vs реестр file_hash.

  python -m kontur.cli.check_storage_integrity

Реестр: ``KONTUR_DB_URL`` (Postgres ``process_files``) или in-memory (smoke).
Тела: object store по env, как у API (``KONTUR_OBJECT_STORE_URL`` ...).

Exit-коды (fail-closed):
  0 — все файлы совпали;
  1 — mismatch / missing / no_hash / invalid_hash / error по любому файлу;
  3 — реестр пуст (0 файлов), если не ``KONTUR_INTEGRITY_ALLOW_EMPTY=1``;
  4 — Postgres без object store (проверять нечего: байты не достижимы);
  5 — реестр/хранилище недоступны (исключение при чтении).

Расхождение пишет audit ``STORAGE_INTEGRITY_MISMATCH`` в ``audit_log``
(Postgres и in-memory). Повтор того же состояния файла (file_id, status, expected,
actual) на следующем прогоне НЕ дублируется; смена состояния — новая запись.
Ошибка чтения/audit по одному файлу не прерывает прогон (статус ``error``).
Не путать с ``payload_sha256`` outbox/RiN.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from kontur.application.wiring import build_object_store, build_process_store
from kontur.infrastructure.storage_integrity import (
    check_storage_integrity,
    registry_from_store,
)

AUDIT_ACTION = "STORAGE_INTEGRITY_MISMATCH"
EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_EMPTY = 3
EXIT_NO_OBJECT_STORE = 4
EXIT_UNAVAILABLE = 5


def _has_object_store() -> bool:
    return bool(
        (os.environ.get("KONTUR_OBJECT_STORE_URL") or "").strip()
        or (os.environ.get("KONTUR_S3_ENDPOINT") or "").strip()
    )


def run(store: Any = None, objects: Any = None) -> int:
    logging.basicConfig(level=logging.INFO)
    is_db = bool((os.environ.get("KONTUR_DB_URL") or "").strip())
    if store is None and is_db and not _has_object_store():
        print(
            "check_storage_integrity: KONTUR_DB_URL без object store — "
            "тела недоступны, проверка невозможна (fail-closed).",
            file=sys.stderr,
        )
        return EXIT_NO_OBJECT_STORE
    try:
        store = store if store is not None else build_process_store()
        objects = objects if objects is not None else build_object_store()
        entries = registry_from_store(store)
    except Exception as exc:  # noqa: BLE001 — любой сбой чтения = fail-closed
        print(f"check_storage_integrity: реестр недоступен: {exc!r}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    if not entries and os.environ.get("KONTUR_INTEGRITY_ALLOW_EMPTY") != "1":
        print(
            "check_storage_integrity: реестр пуст (0 файлов) — fail-closed; "
            "KONTUR_INTEGRITY_ALLOW_EMPTY=1 для осознанного пропуска.",
            file=sys.stderr,
        )
        return EXIT_EMPTY

    seen: dict[str, list[dict[str, object]]] = {}

    def _already_audited(process_id: str, payload: dict[str, object]) -> bool:
        """Тот же файл в том же состоянии уже записан прошлым прогоном?"""

        if process_id not in seen:
            try:
                events = store.load_audit(process_id)
                seen[process_id] = [
                    body for _actor, action, body in events if action == AUDIT_ACTION
                ]
            except Exception:  # noqa: BLE001 — не смогли прочитать: пишем (лучше дубль)
                seen[process_id] = []
        keys = ("file_id", "status", "expected_hash", "actual_hash")
        return any(all(old.get(k) == payload.get(k) for k in keys) for old in seen[process_id])

    def _audit(actor: str, action: str, payload: dict[str, object]) -> None:
        process_id = str(payload["process_id"])
        if _already_audited(process_id, payload):
            logging.getLogger("kontur").info(
                "integrity audit dedup process=%s file=%s status=%s",
                process_id,
                payload["file_id"],
                payload["status"],
            )
            return
        store.save_audit_event(process_id, actor, action, payload)
        seen[process_id].append(payload)

    try:
        report = check_storage_integrity(entries, objects, audit=_audit)
    except Exception as exc:  # noqa: BLE001
        print(f"check_storage_integrity: сбой проверки: {exc!r}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    print(f"ok={report.ok} bad={report.bad}")
    for item in report.findings:
        if item.status == "ok":
            continue
        print(
            f"{item.status}\t{item.process_id}\t{item.file_id}\t"
            f"expected={item.expected_hash}\tactual={item.actual_hash or '-'}"
        )
    return EXIT_OK if report.passed else EXIT_MISMATCH


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
