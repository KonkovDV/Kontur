"""Тесты: put_finding идемпотентность (RT-G, stop-ship п.11), PR #24.

Проблема до фикса:
    `put_finding` хранил находку по `finding_id = uuid4()`.
    При at-least-once retry (toже rule + toже файлы) `evaluate_rule`
    генерировал новый uuid → дубликат в `record.findings`.

Фикс (PR #24):
    Ключ = `evidence_group_id` (comparison_key — детерминированный).
    Повторный put_finding перезаписывает ту же запись, а не добавляет новую.
    Для halted-находок (без evidence_group_id) — finding_id.
Связан: docs/RED_TEAM.md «ретрай создаёт дубликат находки или протокола».
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.models import DocStage, Finding
from kontur.domain.statuses import Completeness, FindingStatus, ReviewPriority

# ── вспомогательные функции ───────────────────────────────────────────────────────────────────

_COMPLETENESS_BOTH = {
    DocStage.PD: Completeness.PRESENT,
    DocStage.RD: Completeness.PRESENT,
    DocStage.ID: Completeness.MISSING,
}


def _workspace_with_process() -> tuple[ProcessWorkspace, str]:
    ws = ProcessWorkspace()
    rec = ws.create(object_id="OBJ-TEST-001", completeness=_COMPLETENESS_BOTH)
    return ws, rec.process_id


def _candidate_finding(group_id: str) -> Finding:
    """Находка CANDIDATE с evidence_group_id (at-least-once path)."""
    return Finding(
        finding_id=str(uuid4()),
        rule_code="TEST-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=group_id,
        rationale="тестовая находка",
    )


def _halted_finding() -> Finding:
    """Находка без evidence_group (halted path: MISSING_EVIDENCE, LOW_QUALITY…)."""
    return Finding(
        finding_id=str(uuid4()),
        rule_code="TEST-002",
        finding_status=FindingStatus.MISSING_EVIDENCE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=None,  # halted — нет evidence_group
        rationale="документ отсутствует",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Основные тесты (RT-G oracle)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPutFindingIdempotency:
    """Идемпотентность `put_finding`: at-least-once retry не дублирует находку."""

    def test_first_put_stores_finding(self) -> None:
        """Первый put — находка сохраняется."""
        ws, pid = _workspace_with_process()
        group_id = "grp-001"
        finding = _candidate_finding(group_id)
        ws.put_finding(pid, finding)
        record = ws.get(pid)
        assert len(record.findings) == 1

    def test_repeated_put_with_same_group_id_no_duplicate(self) -> None:
        """Регрессия RT-G: at-least-once retry — 1 находка, не 2.

        Сценарий: очередь at-least-once доставляет то же сообщение дважды.
        evaluate_rule вызывается дважды: finding_id ≠ (разные uuid4),
        но evidence_group_id тот же — comparison_key(тройка одинаковая).
        """
        ws, pid = _workspace_with_process()
        group_id = "grp-at-least-once-001"

        # Первая доставка
        finding_first = _candidate_finding(group_id)
        ws.put_finding(pid, finding_first)

        # Ретрай (та же rule/files, новый uuid4 finding_id)
        finding_retry = _candidate_finding(group_id)
        assert finding_retry.finding_id != finding_first.finding_id, "uuid4 должен отличаться"
        ws.put_finding(pid, finding_retry)

        record = ws.get(pid)
        assert len(record.findings) == 1, (
            f"at-least-once retry создал {len(record.findings)} находки — ожидалась 1"
        )
        # Храним последнюю версию (retry перезаписывает)
        stored_finding = next(iter(record.findings.values()))
        assert stored_finding.finding_id == finding_retry.finding_id

    def test_different_group_ids_stored_separately(self) -> None:
        """Две разные находки (group_id разные) — хранятся раздельно."""
        ws, pid = _workspace_with_process()
        ws.put_finding(pid, _candidate_finding("grp-rule-001"))
        ws.put_finding(pid, _candidate_finding("grp-rule-002"))
        record = ws.get(pid)
        assert len(record.findings) == 2

    def test_halted_finding_without_group_id_uses_finding_id(self) -> None:
        """Халтед-находка (evidence_group_id=None) — ключ finding_id."""
        ws, pid = _workspace_with_process()
        halted = _halted_finding()
        ws.put_finding(pid, halted)
        record = ws.get(pid)
        assert len(record.findings) == 1
        # ключ в словаре — finding_id
        assert halted.finding_id in record.findings

    def test_two_halted_findings_for_same_rule_stored_separately(self) -> None:
        """Два халта без group_id — независимы записи (finding_id разные)."""
        ws, pid = _workspace_with_process()
        ws.put_finding(pid, _halted_finding())
        ws.put_finding(pid, _halted_finding())
        record = ws.get(pid)
        # Halted-находки без group — не дублируются при нормальном потоке;
        # при retry (id разные) — две записи (safe: дубль MISSING_EVIDENCE не вреден)
        assert len(record.findings) == 2

    def test_candidate_then_retry_counter_stays_at_one(self) -> None:
        """Счётчик candidates: 3 ретрая одного правила — 1 candidate, не 3."""
        ws, pid = _workspace_with_process()
        group_id = "grp-counter-test"
        for _ in range(3):
            ws.put_finding(pid, _candidate_finding(group_id))
        record = ws.get(pid)
        status_data = record.to_status()
        assert status_data["counters"]["candidates"] == 1, (
            f"Ожидался 1 candidate, получен {status_data['counters']['candidates']}"
        )
