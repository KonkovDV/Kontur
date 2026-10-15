"""Object store тел файлов: память для тестов, S3/MinIO для стенда.

Метаданные процесса живут в ProcessStore; байты PDF — здесь.
Ключ объекта: ``{process_id}/{file_id}``.
"""

from __future__ import annotations

from typing import Protocol


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
    """MinIO / S3 через boto3. Bucket создаётся при первом put, если его нет."""

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
        import boto3
        from botocore.client import Config

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def put(self, process_id: str, file_id: str, content: bytes) -> str:
        key = object_key(process_id, file_id)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content)
        return key

    def get(self, process_id: str, file_id: str) -> bytes | None:
        from botocore.exceptions import ClientError

        key = object_key(process_id, file_id)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        body = response["Body"].read()
        return bytes(body)

    def delete(self, process_id: str, file_id: str) -> None:
        self._client.delete_object(
            Bucket=self._bucket, Key=object_key(process_id, file_id)
        )
