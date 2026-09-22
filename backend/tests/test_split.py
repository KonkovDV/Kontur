"""Tests for split() in kontur.application.review (#83 GAP-SPLIT).

Exit criteria (issue #83):
- split(finding, 2) → 2 distinct CANDIDATE findings
- каждая часть: новый finding_id, новый evidence_group_id
- source_id == родительский finding_id
- evidence_refs пустой (провенанс не дублируется)
- audit.record вызван ровно один раз с правильными payload
- fail-closed: не человек / parts<2 / запрещённый статус / FINALIZED
- SPLIT не в ACTION_TO_STATUS; review() бросает TransitionError
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from kontur.application.review import ACTION_TO_STATUS, review, split
from kontur.domain.models import Finding
from kontur.domain.state_machines import Actor, TransitionError
from kontur.domain.statuses import FindingStatus, ProcessState


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def human_actor() -> Actor:
    return Actor(actor_id="inspector-01", is_human=True)


@pytest.fixture()
def bot_actor() -> Actor:
    return Actor(actor_id="pipeline-bot", is_human=False)


@pytest.fixture()
def candidate_finding() -> Finding:
    """Minimal valid CANDIDATE finding."""
    return Finding(
        finding_id="find-001",
        rule_code="RULE-A",
        finding_status=FindingStatus.CANDIDATE,
        evidence_group_id="eg-original",
        evidence_refs=("ref-1", "ref-2"),
        source_id=None,
        inspector_decision=None,
    )


@pytest.fixture()
def clarification_finding(candidate_finding: Finding) -> Finding:
    from dataclasses import replace

    return replace(
        candidate_finding,
        finding_id="find-002",
        finding_status=FindingStatus.CLARIFICATION_REQUIRED,
    )


@pytest.fixture()
def audit() -> MagicMock:
    m = MagicMock()
    m.record = MagicMock()
    return m


# ── happy path ────────────────────────────────────────────────────────────────


class TestSplitHappyPath:
    def test_returns_correct_count(self, candidate_finding, human_actor, audit):
        result = split(candidate_finding, 2, actor=human_actor, audit=audit)
        assert len(result) == 2

    def test_n_way_split(self, candidate_finding, human_actor, audit):
        result = split(candidate_finding, 5, actor=human_actor, audit=audit)
        assert len(result) == 5

    def test_each_part_is_candidate(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 3, actor=human_actor, audit=audit)
        assert all(p.finding_status == FindingStatus.CANDIDATE for p in parts)

    def test_finding_ids_are_unique(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 4, actor=human_actor, audit=audit)
        ids = [p.finding_id for p in parts]
        assert len(set(ids)) == 4, "finding_ids must be globally unique"

    def test_finding_ids_contain_parent(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        assert all(candidate_finding.finding_id in p.finding_id for p in parts)

    def test_evidence_group_ids_are_unique(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 3, actor=human_actor, audit=audit)
        eg_ids = [p.evidence_group_id for p in parts]
        assert len(set(eg_ids)) == 3, "each part must have its own evidence_group_id"

    def test_evidence_group_ids_differ_from_parent(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        for part in parts:
            assert part.evidence_group_id != candidate_finding.evidence_group_id

    def test_source_id_points_to_parent(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        assert all(p.source_id == candidate_finding.finding_id for p in parts)

    def test_evidence_refs_cleared(self, candidate_finding, human_actor, audit):
        """Provenance must not be duplicated: evidence_refs empty on each child."""
        assert candidate_finding.evidence_refs  # sanity: parent has refs
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        assert all(len(p.evidence_refs) == 0 for p in parts)

    def test_inspector_decision_cleared(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        assert all(p.inspector_decision is None for p in parts)

    def test_rule_code_preserved(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        assert all(p.rule_code == candidate_finding.rule_code for p in parts)

    def test_audit_record_called_once(self, candidate_finding, human_actor, audit):
        split(candidate_finding, 2, actor=human_actor, audit=audit)
        audit.record.assert_called_once()

    def test_audit_record_payload(self, candidate_finding, human_actor, audit):
        parts = split(candidate_finding, 2, actor=human_actor, audit=audit)
        actor_id, action, payload = audit.record.call_args[0]
        assert actor_id == human_actor.actor_id
        assert action == "SPLIT"
        assert payload["parent_finding_id"] == candidate_finding.finding_id
        assert payload["parts"] == 2
        assert payload["child_ids"] == [p.finding_id for p in parts]

    def test_clarification_required_is_splittable(
        self, clarification_finding, human_actor, audit
    ):
        parts = split(clarification_finding, 2, actor=human_actor, audit=audit)
        assert len(parts) == 2
        assert all(p.finding_status == FindingStatus.CANDIDATE for p in parts)

    def test_process_state_none_allowed(self, candidate_finding, human_actor, audit):
        """process_state=None (default) must not raise."""
        parts = split(
            candidate_finding, 2, actor=human_actor, audit=audit, process_state=None
        )
        assert len(parts) == 2

    def test_process_state_verifying_allowed(self, candidate_finding, human_actor, audit):
        parts = split(
            candidate_finding,
            2,
            actor=human_actor,
            audit=audit,
            process_state=ProcessState.VERIFYING,
        )
        assert len(parts) == 2


# ── fail-closed ────────────────────────────────────────────────────────────────


class TestSplitFailClosed:
    def test_bot_actor_raises(self, candidate_finding, bot_actor, audit):
        with pytest.raises(TransitionError, match="human"):
            split(candidate_finding, 2, actor=bot_actor, audit=audit)

    def test_parts_one_raises(self, candidate_finding, human_actor, audit):
        with pytest.raises(TransitionError, match=">= 2"):
            split(candidate_finding, 1, actor=human_actor, audit=audit)

    def test_parts_zero_raises(self, candidate_finding, human_actor, audit):
        with pytest.raises(TransitionError, match=">= 2"):
            split(candidate_finding, 0, actor=human_actor, audit=audit)

    def test_parts_negative_raises(self, candidate_finding, human_actor, audit):
        with pytest.raises(TransitionError):
            split(candidate_finding, -1, actor=human_actor, audit=audit)

    def test_confirmed_violation_raises(self, candidate_finding, human_actor, audit):
        from dataclasses import replace

        blocked = replace(
            candidate_finding, finding_status=FindingStatus.CONFIRMED_VIOLATION
        )
        with pytest.raises(TransitionError, match="CONFIRMED_VIOLATION"):
            split(blocked, 2, actor=human_actor, audit=audit)

    def test_negative_verified_raises(self, candidate_finding, human_actor, audit):
        from dataclasses import replace

        blocked = replace(
            candidate_finding, finding_status=FindingStatus.NEGATIVE_VERIFIED
        )
        with pytest.raises(TransitionError):
            split(blocked, 2, actor=human_actor, audit=audit)

    def test_suspicion_raises(self, candidate_finding, human_actor, audit):
        from dataclasses import replace

        blocked = replace(candidate_finding, finding_status=FindingStatus.SUSPICION)
        with pytest.raises(TransitionError):
            split(blocked, 2, actor=human_actor, audit=audit)

    def test_finalized_process_raises(self, candidate_finding, human_actor, audit):
        with pytest.raises(TransitionError, match="FINALIZED"):
            split(
                candidate_finding,
                2,
                actor=human_actor,
                audit=audit,
                process_state=ProcessState.FINALIZED,
            )

    def test_audit_not_called_on_error(
        self, candidate_finding, bot_actor, audit
    ):
        """Audit must not be written if split is rejected."""
        with pytest.raises(TransitionError):
            split(candidate_finding, 2, actor=bot_actor, audit=audit)
        audit.record.assert_not_called()


# ── SPLIT не является action в ReviewDecision ──────────────────────────────────────


class TestSplitNotInReview:
    def test_split_not_in_action_to_status(self):
        assert "SPLIT" not in ACTION_TO_STATUS

    def test_review_raises_for_split_action(self, candidate_finding, human_actor):
        with pytest.raises(TransitionError, match="SPLIT"):
            review(
                candidate_finding,
                actor=human_actor,
                action="SPLIT",
                comment="trying to split via review",
            )
