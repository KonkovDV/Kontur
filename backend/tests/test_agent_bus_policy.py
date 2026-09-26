"""Tracked agent instructions must use one current bus protocol and plan."""

from __future__ import annotations

from kontur.evaluation.agent_dumps import repo_root


def test_contest_slice_agent_uses_bus_v2_and_current_plan() -> None:
    root = repo_root()
    agent_path = root / ".github" / "agents" / "contest-slice.agent.md"
    text = agent_path.read_text(encoding="utf-8")

    assert "kontur.agent_bus.v2" in text
    assert "kontur.agent_bus.v1" not in text
    assert "docs/GH_AGENT_BUS.md" in text
    assert "docs/AGENT_HANDOFF.md" in text
    assert "docs/PLAN_2026_09_26_29.md" in text
    assert "runner_id != 0" in text
    assert "CONFIRMED_VIOLATION" in text


def test_current_plan_keeps_acceptance_gates_open() -> None:
    root = repo_root()
    plan_path = root / "docs" / "PLAN_2026_09_26_29.md"
    text = plan_path.read_text(encoding="utf-8")

    assert "гейты I/J/K/L открыты" in text
    assert "TEST_HIDDEN" in text
    assert "48 executable" in text
    assert "79 extractor_missing" in text
    assert "kontur.agent_bus.v2" in text
    assert "requirement → artifact → test → metric → stop" in text
    assert "#77" in text and "needs-local-files" in text and "human" in text
    assert "#87" in text and "cloud" in text
    assert "рекордер не закрывает Gate K" in text
