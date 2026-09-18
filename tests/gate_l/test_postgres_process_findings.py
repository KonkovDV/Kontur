"""Gate L: PostgresProcessStore.save_finding / load_findings.

Тесты работают с mock-псевдо-connection: никакого реального Postgres не нужно.
Стратегия: емулируем cursor/execute; проверяем SQL и параметры, а не результат бд.

Выученные уроки:
  - Статусы берём из FindingStatus, не хардкодим строки
  - Дедуп по (process_id, finding_id) — upsert, не append
  - MemoryProcessStore и PostgresProcessStore имеют одинаковый интерфейс
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from kontur.domain.statuses import FindingStatus, ReviewPriority
from kontur.infrastructure.db.process_store import (
    FindingSnapshot,
    MemoryProcessStore,
    PostgresProcessStore,
    UPSERT_FINDING_SQL,
    LOAD_FINDINGS_SQL,
    finding_params,
)

# ─────────────────────────────── helpers ─────────────────────────────────────


def _make_finding(
    process_id: str = "proc-1",
    finding_id: str = "find-1",
    status: FindingStatus = FindingStatus.CANDIDATE,
) -> FindingSnapshot:
    return FindingSnapshot(
        process_id=process_id,
        finding_id=finding_id,
        rule_code="IOS4-078",
        finding_status=status,
        evidence_group_id="eg-1",
        expected_value="100.0",
        actual_value="95.0",
        delta="-5.0",
        rationale="delta превышена",
        review_priority=ReviewPriority.HIGH,
        matrix_version="v1.0",
        missing_stage=None,
    )


class _FakeCursor:
    """Cursor, который fetchall/fetchone возвращает предзагруженные данные."""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return self._rows


class _MockConnection:
    """Псевдо-подключение: пишем вызовы, возвращаем _FakeCursor."""

    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows: list[tuple] = rows or []
        self.calls: list[tuple[str, dict]] = []  # (sql, params)

    def execute(self, sql: str, params: dict) -> _FakeCursor:
        self.calls.append((sql.strip(), params))
        return _FakeCursor(self._rows)


# ─────────────────────────────── MemoryProcessStore tests ────────────────────


def test_memory_save_and_load_finding() -> None:
    store = MemoryProcessStore()
    f = _make_finding()
    store.save_finding(f)
    loaded = store.load_findings("proc-1")
    assert len(loaded) == 1
    assert loaded[0].finding_id == "find-1"
    assert loaded[0].finding_status is FindingStatus.CANDIDATE


def test_memory_load_findings_empty() -> None:
    store = MemoryProcessStore()
    assert store.load_findings("proc-999") == []


def test_memory_finding_dedup() -> None:
    """Повторный save_finding с тем же finding_id заменяет запись (upsert)."""
    store = MemoryProcessStore()
    f1 = _make_finding(status=FindingStatus.CANDIDATE)
    f2 = _make_finding(status=FindingStatus.AUTO_NO_DIFFERENCE)
    store.save_finding(f1)
    store.save_finding(f2)
    loaded = store.load_findings("proc-1")
    assert len(loaded) == 1
    assert loaded[0].finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_memory_findings_isolated_by_process() -> None:
    store = MemoryProcessStore()
    store.save_finding(_make_finding(process_id="proc-A", finding_id="f1"))
    store.save_finding(_make_finding(process_id="proc-B", finding_id="f2"))
    assert len(store.load_findings("proc-A")) == 1
    assert len(store.load_findings("proc-B")) == 1
    assert store.load_findings("proc-A")[0].finding_id == "f1"


# ─────────────────────────────── PostgresProcessStore tests ──────────────────


def test_postgres_save_finding_calls_upsert() -> None:
    conn = _MockConnection()
    store = PostgresProcessStore(conn)
    f = _make_finding()
    store.save_finding(f)
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "process_findings" in sql
    assert "ON CONFLICT" in sql
    assert params["finding_id"] == "find-1"
    assert params["finding_status"] == FindingStatus.CANDIDATE.value


def test_postgres_save_finding_status_value_from_enum() -> None:
    """finding_status — .value строки из enum, не хардкод ."""
    conn = _MockConnection()
    store = PostgresProcessStore(conn)
    for status in [
        FindingStatus.CANDIDATE,
        FindingStatus.AUTO_NO_DIFFERENCE,
        FindingStatus.MISSING_EVIDENCE,
        FindingStatus.ABSTAIN,
    ]:
        f = _make_finding(finding_id=status.value, status=status)
        store.save_finding(f)
        _, params = conn.calls[-1]
        assert params["finding_status"] == status.value


def test_postgres_load_findings_returns_snapshots() -> None:
    f = _make_finding()
    row = (
        f.process_id, f.finding_id, f.rule_code, f.finding_status.value,
        f.evidence_group_id, f.expected_value, f.actual_value, f.delta,
        f.rationale, f.review_priority.value, f.matrix_version, f.missing_stage,
    )
    conn = _MockConnection(rows=[row])
    store = PostgresProcessStore(conn)
    loaded = store.load_findings("proc-1")
    assert len(loaded) == 1
    snap = loaded[0]
    assert snap.finding_id == "find-1"
    assert snap.finding_status is FindingStatus.CANDIDATE
    assert snap.review_priority is ReviewPriority.HIGH
    assert snap.missing_stage is None


def test_postgres_load_findings_empty() -> None:
    conn = _MockConnection(rows=[])
    store = PostgresProcessStore(conn)
    assert store.load_findings("proc-999") == []


def test_finding_params_no_hardcoded_strings() -> None:
    """finding_params берёт .value из enum — нет хардкода."""
    f = _make_finding(status=FindingStatus.LOW_QUALITY)
    params = finding_params(f)
    assert params["finding_status"] == FindingStatus.LOW_QUALITY.value
    assert params["review_priority"] == ReviewPriority.HIGH.value
