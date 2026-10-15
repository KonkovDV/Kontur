"""Object store тел файлов: память для тестов, S3/MinIO для стенда.

Метаданные процесса живут в ProcessStore; байты PDF — здесь.
Ключ объекта: ``{process_id}/{file_id}``.

S3-клиент создаётся лениво: lifespan API не падает, если MinIO ещё не в DNS
(smoke/partial compose). Bucket — при первом put/get.
"""

from __future__ import annotations

from typing import Any, Protocol


class ObjectStore(Protocol):
    def put(self, process_id: str, file_id: str, content: bytes) -> str:
        """Записать тело; вернуть ключ хранения."""

    def get(self, process_id: str, file_id: str) -> bytes | None:
        """Прочитать тело или None, если ключа нет."""

    def delete(self, process_id: str, file_id: str) -> None:
        """Удалить тело, если есть. Отсутствие ключа — не ошибка."""


def object_key(process_id: str, file_id: str) -> str:
    if not process_id.strip() or not file_id.strip():
        raise ValueError("process_id и file_id обязательны")
    if "/" in process_id or "/" in file_id:
        raise ValueError("process_id и file_id не должны содержать '/'")
    return f"{process_id}/{file_id}"


class MemoryObjectStore:
    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}

    def put(self, process_id: str, file_id: str, content: bytes) -> str:
        key = object_key(process_id, file_id)
        self._items[key] = content
        return key

    def get(self, process_id: str, file_id: str) -> bytes | None:
        return self._items.get(object_key(process_id, file_id))

    def delete(self, process_id: str, file_id: str) -> None:
        self._items.pop(object_key(process_id, file_id), None)

    def clear(self) -> None:
        self._items.clear()


class S3ObjectStore:
    """MinIO / S3 через boto3. Клиент и bucket — при первом обращении."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        if not endpoint_url.strip() or not bucket.strip():
            raise ValueError("endpoint_url и bucket обязательны")
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._client = None
        self._bucket_ready = False

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3  # type: ignore[import-not-found,import-untyped,unused-ignore]
            from botocore.client import Config  # type: ignore[import-not-found,import-untyped,unused-ignore]

            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
                config=Config(signature_version="s3v4"),
            )
        return self._client

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        from botocore.exceptions import ClientError  # type: ignore[import-not-found,import-untyped,unused-ignore]

        client = self._get_client()
        try:
            client.head_bucket(Bucket=self._bucket)
        except ClientError:
            client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True

    def put(self, process_id: str, file_id: str, content: bytes) -> str:
        self._ensure_bucket()
        key = object_key(process_id, file_id)
        self._get_client().put_object(Bucket=self._bucket, Key=key, Body=content)
        return key

    def get(self, process_id: str, file_id: str) -> bytes | None:
        from botocore.exceptions import ClientError  # type: ignore[import-not-found,import-untyped,unused-ignore]

        self._ensure_bucket()
        key = object_key(process_id, file_id)
        try:
            response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return bytes(response["Body"].read())

    def delete(self, process_id: str, file_id: str) -> None:
        self._ensure_bucket()
        self._get_client().delete_object(
            Bucket=self._bucket, Key=object_key(process_id, file_id)
        )
