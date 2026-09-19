"""Снимки handoff: гейты закрыть нельзя, coverage не выдаёт 132 executable за порог."""

from __future__ import annotations

import json

from kontur.evaluation.agent_dumps import (
    build_coverage_snapshot,
    build_handoff,
    coverage_path,
    export_all,
    handoff_path,
    repo_root,
)
from kontur.evaluation.dataset_package import LABELED_TRAIN_OBJECT_IDS
from kontur.evaluation.frozen_val import critical_recall, load_frozen_val_jsonl, recall_meets_tz
from kontur.evaluation.train_public import TrainPublicFile, summarize_index
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry


def test_coverage_snapshot_matches_registry() -> None:
    live = build_coverage_snapshot()
    counts = live["counts"]
    assert isinstance(counts, dict)
    assert counts["declared"] == EXPECTED_PARAM_COUNT
    assert counts["expected_total"] == EXPECTED_PARAM_COUNT
    assert int(counts["executable"]) >= 20
    assert int(counts["executable"]) < EXPECTED_PARAM_COUNT
    assert live["closes_gate_j"] is False
    assert live["executable_equals_declared"] is False
    codes = live["codes"]
    assert isinstance(codes, dict)
    executable = codes["executable"]
    assert isinstance(executable, list)
    assert "IOS4-078" in executable
    assert "IOS4-079" in executable
    assert "PZ-001" in executable
    registry = FileRuleRegistry()
    assert counts == registry.coverage_report()


def test_handoff_refuses_to_close_gates() -> None:
    payload = build_handoff()
    assert payload["closes_gate_i"] is False
    assert payload["closes_gate_j"] is False
    assert payload["closes_gate_k"] is False
    assert payload["closes_gate_l"] is False
    assert payload["hidden_test_contents_inspected"] is False
    assert set(payload["allowlist_object_ids"]) == set(LABELED_TRAIN_OBJECT_IDS)
    assert "OBJ-RECHNIKOV-7-7" in payload["hidden_test_object_ids"]
    assert payload["gold_matrix_positives"] == 6
    assert payload["wilson_perfect_n_min_recall"] == 16
    assert "GAP-IOS4-VAL" in payload["open_gaps"]
    assert "GAP-CAP-OCR" in payload["open_gaps"]
    assert "GAP-K6-P95" not in payload["open_gaps"]
    steps = payload["work_plan_steps"]
    assert isinstance(steps, dict)
    assert steps["5_gate_l_k6"] == "measured_on_gha_not_production_sla"
    do_not = " ".join(str(item) for item in payload["do_not"])
    assert "TEST_HIDDEN" in do_not
    assert "CONFIRMED_VIOLATION" in do_not
    echo = payload["verdict_echo"]
    assert isinstance(echo, dict)
    assert echo["closes_gate_j"] is False
    assert echo["frozen_validation_corpus_for_132"] is False


def test_committed_dumps_match_builder() -> None:
    root = repo_root()
    coverage_file = json.loads(coverage_path(root).read_text(encoding="utf-8"))
    handoff_file = json.loads(handoff_path(root).read_text(encoding="utf-8"))
    live_cov = build_coverage_snapshot()
    assert coverage_file["counts"] == live_cov["counts"]
    assert coverage_file["codes"] == live_cov["codes"]
    assert handoff_file["closes_gate_j"] is False
    assert handoff_file["coverage_counts"] == live_cov["counts"]
    doc = root / "docs" / "AGENT_HANDOFF.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "agent_handoff.json" in text
    assert "не закрыт" in text.lower() or "открыт" in text.lower()


def test_summarize_index_skips_mixed_without_files() -> None:
    index = (
        TrainPublicFile(
            file_id="F1",
            object_id="OBJ-NOVOSLOBODSKAYA",
            stage_raw="PD",
            source_relative_path="Документация/a.pdf",
            output_pdf="annotated_documents/F1.pdf",
        ),
        TrainPublicFile(
            file_id="F2",
            object_id="OBJ-TYUMENSKAYA-5-GOLD-SEED",
            stage_raw="RD_ID_MIXED",
            source_relative_path="Документация/b.pdf",
            output_pdf="annotated_documents/F2.pdf",
        ),
    )
    stats = summarize_index(index, excluded=frozenset())
    assert stats["n_index"] == 2
    assert stats["n_runnable_stage"] == 1
    assert stats["closes_gate_j"] is False
    assert stats["tyumen_has_rd"] is False
    stages = stats["by_stage"]
    assert isinstance(stages, dict)
    assert stages["RD_ID_MIXED"] == 1


def test_committed_index_stats_do_not_close_gate_j() -> None:
    root = repo_root()
    path = root / "data" / "dataset" / "train_public_index_stats.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["n_index"] == 203
    assert payload["closes_gate_j"] is False
    assert payload["tyumen_has_rd"] is False
    assert payload["tyumen_has_id"] is False
    assert payload["by_stage"]["RD_ID_MIXED"] == 10
    assert "OBJ-RECHNIKOV-7-7" not in payload["by_object"]


def test_engineering_dump_and_pred_jsonl_keep_gate_j_open() -> None:
    root = repo_root()
    report = json.loads(
        (root / "data" / "dataset" / "train_public_engineering.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["closes_gate_j"] is False
    assert report["recall_meets_tz"] is False
    assert report["gap_ios4_val_open"] is True
    assert report["gold_mixed_loaded_as"] == "RD"
    assert report["n_gold_matrix"] == 6
    assert report["recall_n"] == 6
    assert report["stage_page_model"] == "gold_evidence_mixed_as_rd"
    gold_ids = report["gold_file_ids"]
    assert isinstance(gold_ids, list)
    assert "F0171" in gold_ids
    assert "F0201" in gold_ids
    assert "F0202" not in gold_ids
    hits = int(report["hits"])
    assert 0 <= hits <= 6
    rows = load_frozen_val_jsonl(root / "data" / "dataset" / "train_public_pred.jsonl")
    assert len(rows) == 6
    assert all(row.object_id == "OBJ-TYUMENSKAYA-5-GOLD-SEED" for row in rows)
    assert all(row.gold_positive for row in rows)
    assert sum(1 for row in rows if row.predicted_positive) == hits
    interval = critical_recall(
        [row.gold_positive for row in rows],
        [row.predicted_positive for row in rows],
    )
    assert not recall_meets_tz(interval)


def test_export_all_writes_json() -> None:
    written = export_all(repo_root())
    assert written["coverage"].is_file()
    assert written["handoff"].is_file()


def test_handoff_pointer_files_exist() -> None:
    root = repo_root()
    payload = json.loads(handoff_path(root).read_text(encoding="utf-8"))
    pointers = payload["pointers"]
    assert isinstance(pointers, dict)
    for rel in pointers.values():
        assert isinstance(rel, str)
        target = root / rel
        assert target.is_file(), rel
