"""Сборка ProcessWorkspace: Postgres + MinIO/S3 вместо иллюзии compose.

Без KONTUR_DB_URL — MemoryProcessStore (pytest).
С KONTUR_DB_URL — ConnectingPostgresProcessStore (без пула соединений).
KONTUR_OBJECT_STORE_URL (или KONTUR_S3_ENDPOINT) — S3ObjectStore, иначе MemoryObjectStore.
В non-dev (не dev/test/local/demo) DB без object store — fail startup:
иначе метаданные «durable», а байты снова только в RAM.
Auth/clamd/RabbitMQ в этот модуль не входят.
"""

from __future__ import annotations

import os
from typing import Any

from kontur.application.runtime import ProcessWorkspace
from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.object_store import MemoryObjectStore, ObjectStore, S3ObjectStore

_DEV_ENVS = frozenset({"dev", "test", "local", "demo"})


def _env_name() -> str:
    return (os.environ.get("KONTUR_ENV") or "dev").strip().lower()


def _object_store_endpoint() -> str:
    return (os.environ.get("KONTUR_OBJECT_STORE_URL") or "").strip() or (
        os.environ.get("KONTUR_S3_ENDPOINT") or ""
    ).strip()


def build_object_store() -> ObjectStore:
    endpoint = _object_store_endpoint()
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
    dsn = (os.environ.get("KONTUR_DB_URL") or "").strip()
    endpoint = _object_store_endpoint()
    if dsn and not endpoint and _env_name() not in _DEV_ENVS:
        raise RuntimeError(
            "KONTUR_DB_URL задан без KONTUR_OBJECT_STORE_URL / KONTUR_S3_ENDPOINT "
            f"при KONTUR_ENV={_env_name()!r}: метаданные уйдут в Postgres, а байты "
            "останутся только в RAM (иллюзия durable). Задайте object store либо "
            "уберите DB URL, либо используйте KONTUR_ENV=dev|demo|test|local."
        )
    return ProcessWorkspace(store=build_process_store(), objects=build_object_store())
