"""Публичный gold организатора не закрывает гейт J."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from kontur.evaluation.dataset_package import (
    GOLD_INVENTORY_PATH,
    HIDDEN_TEST_OBJECT_IDS,
    LABELED_TRAIN_OBJECT_IDS,
    load_gold_inventory,
)
from kontur.evaluation.metrics import meets_threshold, wilson

REPO_DOC = GOLD_INVENTORY_PATH.parents[2] / "docs" / "ORGANIZER_GOLD.md"


def test_gold_inventory_is_in_repository() -> None:
    assert GOLD_INVENTORY_PATH.is_file()
    assert REPO_DOC.is_file()
    text = REPO_DOC.read_text(encoding="utf-8")
    assert "gold_inventory.json" in text
    assert "не закрыт" in text.replace("*", "").lower()


def test_gold_inventory_refuses_to_close_gate_j() -> None:
    payload = load_gold_inventory()
    verdict = payload["verdict"]
    assert isinstance(verdict, Mapping)
    assert verdict["documents_received"] is True
    assert verdict["frozen_validation_corpus_for_132"] is False
    assert verdict["closes_gate_j"] is False
    assert verdict["closes_gate_i"] is False
    assert verdict["closes_gate_k"] is False
    assert verdict["closes_gate_l"] is False
    assert payload["hidden_test_contents_inspected"] is False


def test_organizer_split_has_no_validation() -> None:
    split = load_gold_inventory()["organizer_split"]
    assert isinstance(split, Mapping)
    assert set(split["train_public"]) == set(LABELED_TRAIN_OBJECT_IDS)
    assert set(split["test_hidden"]) == set(HIDDEN_TEST_OBJECT_IDS)
    assert split["validation"] == []
    assert "OBJ-RECHNIKOV-7-7" not in split["train_public"]


def test_public_gold_counts_are_internally_consistent() -> None:
    payload = load_gold_inventory()
    checks = payload["public_gold_checks"]
    assert isinstance(checks, Mapping)
    rows = checks["rows"]
    assert isinstance(rows, list)
    assert len(rows) == 15
    assert checks["n"] == 15
    assert checks["violation_present"] == 10
    assert checks["no_violation"] == 5
    assert checks["score_eligible_true"] == 10
    assert checks["score_eligible_false"] == 5
    assert checks["free_search_score_eligible"] == 4
    assert checks["score_eligible_violation_present_in_matrix"] == 6
    assert checks["confirmed_negative_in_passport"] == 0
    assert checks["unlabeled_is_not_no_violation"] is True

    ids = [row["check_id"] for row in rows if isinstance(row, Mapping)]
    assert ids == [f"TRAIN-{index:04d}" for index in range(1, 16)]
    assert all(isinstance(row, Mapping) and "object_id" in row for row in rows)

    eligible_matrix = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row["score_eligible"] is True
        and row["violation_label"] == "VIOLATION_PRESENT"
        and row["matrix_scope"] == "MATRIX"
    ]
    assert len(eligible_matrix) == 6
    assert {row["parameter_code"] for row in eligible_matrix} == {"IOS4-078", "IOS4-079"}

    free_search = [
        row
        for row in rows
        if isinstance(row, Mapping) and row["parameter_code"] == "FREE-HEATING-001"
    ]
    assert len(free_search) == 4
    assert all(row["matrix_scope"] == "FREE_SEARCH" for row in free_search)


def test_auto_field_candidates_are_not_marked_gold() -> None:
    annotations = load_gold_inventory()["train_public_annotations"]
    assert isinstance(annotations, Mapping)
    assert annotations["n_annotations"] == 30318
    assert annotations["all_split"] == "TRAIN_PUBLIC"
    assert annotations["matrix_field_is_gold"] is False
    assert annotations["matrix_field_status"] == "AUTO_FIELD_CANDIDATE"
    by_status = annotations["by_status"]
    assert isinstance(by_status, Mapping)
    assert by_status["FINAL_GOLD_EXISTENCE"] == 20
    assert by_status["AUTO_FIELD_CANDIDATE"] == 30286


def test_matrix_gold_seed_cannot_meet_tz_recall_even_if_perfect() -> None:
    """n=6 позитивов при 6/6 не берёт порог recall ТЗ по Wilson."""

    constraints = load_gold_inventory()["derived_constraints"]
    assert isinstance(constraints, Mapping)
    n = int(constraints["matrix_score_eligible_positives"])
    assert n == 6
    assert constraints["perfect_six_meets_tz_recall"] is False
    assert constraints["critical_106_labeled"] is False
    interval = wilson(n, n)
    assert not meets_threshold("recall", interval)

    needed = 1
    while not meets_threshold("recall", wilson(needed, needed)):
        needed += 1
    assert needed == int(constraints["perfect_n_min_to_meet_tz_recall"])
    assert needed == 16


def test_workspace_observation_keeps_hidden_test_unopened() -> None:
    workspace = load_gold_inventory()["workspace_observation"]
    assert isinstance(workspace, Mapping)
    assert workspace["in_git"] is False
    assert workspace["hidden_test_unpacked_beside_train"] is True
    names = workspace["present_top_level"]
    assert isinstance(names, list)
    assert any("TEST__213" in str(name) for name in names)
    forbidden = load_gold_inventory()["forbidden"]
    assert isinstance(forbidden, list)
    blob = " ".join(str(item) for item in forbidden)
    assert "TEST__213" in blob or "TEST_HIDDEN" in blob or "скрыт" in blob.lower()


def test_loader_rejects_inventory_that_closes_gate_j(tmp_path: Path) -> None:
    payload = load_gold_inventory()
    verdict = payload["verdict"]
    assert isinstance(verdict, dict)
    verdict["closes_gate_j"] = True
    path = tmp_path / "gold_inventory.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="гейт J"):
        load_gold_inventory(path)


def test_loader_rejects_claim_that_hidden_test_was_read(tmp_path: Path) -> None:
    payload = load_gold_inventory()
    payload["hidden_test_contents_inspected"] = True
    path = tmp_path / "gold_inventory.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="TEST_HIDDEN"):
        load_gold_inventory(path)
