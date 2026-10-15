"""Сборка ProcessWorkspace: Postgres + MinIO/S3 вместо иллюзии compose.

Без KONTUR_DB_URL — MemoryProcessStore (pytest).
С KONTUR_DB_URL — ConnectingPostgresProcessStore.
KONTUR_OBJECT_STORE_URL (или KONTUR_S3_ENDPOINT) — S3ObjectStore, иначе MemoryObjectStore.
Auth/clamd/RabbitMQ в этот модуль не входят.
"""

from __future__ import annotations

import os
from typing import Any

from kontur.application.runtime import ProcessWorkspace
from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.object_store import MemoryObjectStore, ObjectStore, S3ObjectStore


def build_object_store() -> ObjectStore:
    endpoint = (
        (os.environ.get("KONTUR_OBJECT_STORE_URL") or "").strip()
        or (os.environ.get("KONTUR_S3_ENDPOINT") or "").strip()
    )
    if not endpoint:
        return MemoryObjectStore()
    return S3ObjectStore(
        endpoint_url=endpoint,
        access_key=os.environ.get("KONTUR_S3_ACCESS_KEY")
        or os.environ.get("MINIO_ROOT_USER")
        or "kontur",
        secret_key=os.environ.get("KONTUR_S3_SECRET_KEY")
        or os.environ.get("MINIO_ROOT_PASSWORD")
        or "kontur-dev-secret",
        bucket=os.environ.get("KONTUR_S3_BUCKET") or "kontur",
        region=os.environ.get("KONTUR_S3_REGION") or "us-east-1",
    )


def build_process_store() -> Any:
    dsn = (os.environ.get("KONTUR_DB_URL") or "").strip()
    if not dsn:
        return MemoryProcessStore()
    from kontur.infrastructure.db.connecting_store import ConnectingPostgresProcessStore

    return ConnectingPostgresProcessStore(dsn)


def build_workspace() -> ProcessWorkspace:
    return ProcessWorkspace(store=build_process_store(), objects=build_object_store())
