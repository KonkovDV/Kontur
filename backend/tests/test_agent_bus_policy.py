"""Инварианты и исторический план держат открытые гейты приёмки."""

from __future__ import annotations

from kontur.evaluation.agent_dumps import repo_root


def test_invariants_keep_inspector_verdict() -> None:
    root = repo_root()
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "CONFIRMED_VIOLATION" in text
    assert "инспектор" in text.lower()


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
