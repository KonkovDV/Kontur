"""§13 п.8: сверка SHA-256 тел в ObjectStore с реестром file_hash.

Обход идёт от реестра (process_files / MemoryProcessStore), не от S3 list.
Расхождение или отсутствующий blob → mismatch (fail-closed для cron/CI).
Это не ``payload_sha256`` протокола РиН и не evidence-card hash.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from kontur.infrastructure.db.process_store import MemoryProcessStore, ProcessSnapshot
from kontur.infrastructure.object_store import ObjectStore

IntegrityStatus = Literal["ok", "mismatch", "missing"]

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


def registry_from_memory(store: MemoryProcessStore) -> tuple[RegistryFile, ...]:
    """Все файлы из снимков MemoryProcessStore (тесты / in-memory стенд)."""

    rows: list[RegistryFile] = []
    for snapshot in _iter_memory_snapshots(store):
        for item in snapshot.files:
            digest = item.file_hash.strip().lower()
            if not digest:
                continue
            rows.append(
                RegistryFile(
                    process_id=snapshot.process_id,
                    file_id=item.file_id,
                    expected_hash=digest,
                )
            )
    return tuple(rows)


def _iter_memory_snapshots(store: MemoryProcessStore) -> Sequence[ProcessSnapshot]:
    # Публичного list нет: для integrity S достаточно обхода внутреннего реестра.
    return tuple(store._rows.values())  # noqa: SLF001


def check_storage_integrity(
    entries: Iterable[RegistryFile],
    objects: ObjectStore,
    *,
    audit: AuditSink | None = None,
) -> IntegrityReport:
    """Пересчитать sha256(blob) и сравнить с expected_hash из реестра."""

    findings: list[IntegrityFinding] = []
    ok = 0
    bad = 0
    for entry in entries:
        expected = entry.expected_hash.strip().lower()
        blob = objects.get(entry.process_id, entry.file_id)
        if blob is None:
            finding = IntegrityFinding(
                process_id=entry.process_id,
                file_id=entry.file_id,
                expected_hash=expected,
                actual_hash=None,
                status="missing",
            )
            bad += 1
            findings.append(finding)
            _emit_mismatch(finding, audit=audit)
            continue
        actual = hashlib.sha256(blob).hexdigest()
        if actual == expected:
            ok += 1
            findings.append(
                IntegrityFinding(
                    process_id=entry.process_id,
                    file_id=entry.file_id,
                    expected_hash=expected,
                    actual_hash=actual,
                    status="ok",
                )
            )
            continue
        finding = IntegrityFinding(
            process_id=entry.process_id,
            file_id=entry.file_id,
            expected_hash=expected,
            actual_hash=actual,
            status="mismatch",
        )
        bad += 1
        findings.append(finding)
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
