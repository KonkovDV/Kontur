"""§13 п.8: сверка SHA-256 тел в ObjectStore с реестром file_hash.

Обход идёт от реестра (process_files / MemoryProcessStore), не от S3 list.
Расхождение или отсутствующий blob → mismatch (fail-closed для cron/CI).
Это не ``payload_sha256`` протокола РиН и не evidence-card hash.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.object_store import ObjectStore

IntegrityStatus = Literal["ok", "mismatch", "missing", "no_hash", "invalid_hash", "error"]

logger = logging.getLogger("kontur")


@dataclass(frozen=True, slots=True)
class RegistryFile:
    process_id: str
    file_id: str
    expected_hash: str


@dataclass(frozen=True, slots=True)
class IntegrityFinding:
    process_id: str
    file_id: str
    expected_hash: str
    actual_hash: str | None
    status: IntegrityStatus


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    ok: int
    bad: int
    findings: tuple[IntegrityFinding, ...]

    @property
    def passed(self) -> bool:
        return self.bad == 0


AuditSink = Callable[[str, str, dict[str, object]], None]


class FileRegistry(Protocol):
    def list_all_files(self) -> list[tuple[str, str, str]]: ...


def registry_from_store(store: FileRegistry) -> tuple[RegistryFile, ...]:
    """Все файлы реестра (Memory или Postgres) через ``list_all_files()``.

    Пустой file_hash НЕ пропускается: check_storage_integrity пометит no_hash.
    """

    return tuple(
        RegistryFile(process_id=pid, file_id=fid, expected_hash=digest.strip().lower())
        for pid, fid, digest in store.list_all_files()
    )


def registry_from_memory(store: MemoryProcessStore) -> tuple[RegistryFile, ...]:
    return registry_from_store(store)


_HEX64 = re.compile(r"[0-9a-f]{64}")
CHUNK_SIZE = 1 << 20


def _sha256_of(objects: ObjectStore, process_id: str, file_id: str) -> str | None:
    """sha256 тела; потоково (1 МиБ), если стор умеет ``iter_chunks`` — иначе ``get``.

    None — тела нет. Исключения стора пробрасываются (обрабатываются по файлу).
    """

    streamer = getattr(objects, "iter_chunks", None)
    if callable(streamer):
        chunks = streamer(process_id, file_id, CHUNK_SIZE)
        if chunks is None:
            return None
        digest = hashlib.sha256()
        for chunk in chunks:
            digest.update(chunk)
        return digest.hexdigest()
    blob = objects.get(process_id, file_id)
    return None if blob is None else hashlib.sha256(blob).hexdigest()


def check_storage_integrity(
    entries: Iterable[RegistryFile],
    objects: ObjectStore,
    *,
    audit: AuditSink | None = None,
) -> IntegrityReport:
    """Пересчитать sha256(blob) и сравнить с expected_hash из реестра.

    Ошибка по одному файлу (S3, audit) не прерывает прогон: файл получает
    статус ``error`` (или остаётся с своим статусом), остальные проверяются.
    """

    findings: list[IntegrityFinding] = []
    ok = 0
    bad = 0
    for entry in entries:
        expected = entry.expected_hash.strip().lower()
        actual: str | None = None
        if not expected:
            status: IntegrityStatus = "no_hash"
        elif not _HEX64.fullmatch(expected):
            status = "invalid_hash"
        else:
            try:
                actual = _sha256_of(objects, entry.process_id, entry.file_id)
            except Exception:  # noqa: BLE001 — один файл не должен ронять прогон
                logger.exception(
                    "storage integrity read error process=%s file=%s",
                    entry.process_id,
                    entry.file_id,
                )
                status = "error"
            else:
                if actual is None:
                    status = "missing"
                elif actual == expected:
                    status = "ok"
                else:
                    status = "mismatch"
        finding = IntegrityFinding(
            process_id=entry.process_id,
            file_id=entry.file_id,
            expected_hash=expected,
            actual_hash=actual,
            status=status,
        )
        findings.append(finding)
        if status == "ok":
            ok += 1
            continue
        bad += 1
        _emit_mismatch(finding, audit=audit)
    return IntegrityReport(ok=ok, bad=bad, findings=tuple(findings))


def _emit_mismatch(finding: IntegrityFinding, *, audit: AuditSink | None) -> None:
    logger.error(
        "storage integrity %s process=%s file=%s expected=%s actual=%s",
        finding.status,
        finding.process_id,
        finding.file_id,
        finding.expected_hash,
        finding.actual_hash or "-",
    )
    if audit is None:
        return
    try:
        audit(
            "system:integrity",
            "STORAGE_INTEGRITY_MISMATCH",
            {
                "process_id": finding.process_id,
                "file_id": finding.file_id,
                "expected_hash": finding.expected_hash,
                "actual_hash": finding.actual_hash,
                "status": finding.status,
            },
        )
    except Exception:  # noqa: BLE001 — сбой audit не маскирует остальные находки
        logger.exception(
            "storage integrity audit write failed process=%s file=%s",
            finding.process_id,
            finding.file_id,
        )
