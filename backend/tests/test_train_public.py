"""Harness TRAIN_PUBLIC: object_id обязателен, 6/6 не закрывает гейт J."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_pdf_tokens import ascii_pdf

from kontur.application.process_pipeline import PipelineFile
from kontur.domain.models import DocStage
from kontur.domain.statuses import FindingStatus
from kontur.evaluation.frozen_val import FrozenValRow, load_frozen_val_jsonl, recall_meets_tz
from kontur.evaluation.inventory import QuarantineViolation
from kontur.evaluation.metrics import wilson
from kontur.evaluation.train_public import (
    TRAIN_PUBLIC_ENV,
    GoldEvidenceFile,
    RunStats,
    TrainPublicFile,
    build_report,
    collect_candidates,
    discover_train_public_root,
    is_overlay_relative,
    is_predicted_positive,
    load_files_index,
    load_gold_evidence_files,
    loaded_stage_for_gold,
    matrix_gold_checks,
    parse_doc_stage,
    pred_payload,
    resolve_source_pdf,
    resolve_train_public_path,
    run_object_files,
    score_gold_rows,
    select_gold_evidence_blobs,
    select_object_blobs,
)


def _row(
    *,
    file_id: str = "F0001",
    object_id: str = "OBJ-NOVOSLOBODSKAYA",
    stage: str = "PD",
    source: str = "Документация/a.pdf",
    overlay: str = "01_TRAIN_PUBLIC/annotated_documents/F0001.pdf",
) -> TrainPublicFile:
    return TrainPublicFile(
        file_id=file_id,
        object_id=object_id,
        stage_raw=stage,
        source_relative_path=source,
        output_pdf=overlay,
    )


def test_parse_doc_stage_keeps_pd_rd_id() -> None:
    assert parse_doc_stage("PD") is DocStage.PD
    assert parse_doc_stage("RD") is DocStage.RD
    assert parse_doc_stage("ID") is DocStage.ID


def test_mixed_and_unknown_stages_are_not_guessed() -> None:
    assert parse_doc_stage("RD_ID_MIXED") is None
    assert parse_doc_stage("UNKNOWN") is None
    assert parse_doc_stage("") is None


def test_predicted_positive_is_candidate_only() -> None:
    assert is_predicted_positive(FindingStatus.CANDIDATE) is True
    assert is_predicted_positive(FindingStatus.CONFIRMED_VIOLATION) is False
    assert is_predicted_positive(FindingStatus.AUTO_NO_DIFFERENCE) is False
    assert is_predicted_positive(FindingStatus.MISSING_EVIDENCE) is False
    assert is_predicted_positive(FindingStatus.ABSTAIN) is False


def test_overlay_relative_is_rejected() -> None:
    assert is_overlay_relative("01_TRAIN_PUBLIC/annotated_documents/F0001.pdf") is True
    assert is_overlay_relative("Документация/Новослободская/a.pdf") is False


def test_train_public_path_is_none_without_env() -> None:
    assert resolve_train_public_path({}) is None


def test_train_public_path_refuses_quarantine() -> None:
    with pytest.raises(QuarantineViolation):
        resolve_train_public_path({TRAIN_PUBLIC_ENV: "data/quarantine/test_hidden"})


def test_discover_ignores_hidden_test(tmp_path: Path) -> None:
    files = tmp_path / "files"
    (files / "РАЗМЕЧЕННЫЙ_TEST__213").mkdir(parents=True)
    train = files / "РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203"
    train.mkdir()
    found = discover_train_public_root(tmp_path)
    assert found == train


def test_load_files_index_skips_hidden_and_requires_object_id(tmp_path: Path) -> None:
    jsonl = tmp_path / "data" / "files_index.jsonl"
    jsonl.parent.mkdir()
    payload = [
        {
            "file_id": "F1",
            "object_id": "OBJ-NOVOSLOBODSKAYA",
            "stage": "PD",
            "source_relative_path": "Документация/a.pdf",
            "output_pdf": "annotated_documents/F1.pdf",
        },
        {
            "file_id": "F-hid",
            "object_id": "OBJ-RECHNIKOV-7-7",
            "stage": "PD",
            "source_relative_path": "Документация/hid.pdf",
            "output_pdf": "annotated_documents/hid.pdf",
        },
    ]
    jsonl.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in payload) + "\n",
        encoding="utf-8",
    )
    rows = load_files_index(tmp_path)
    assert [item.object_id for item in rows] == ["OBJ-NOVOSLOBODSKAYA"]

    bad = tmp_path / "nested" / "data" / "files_index.jsonl"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        json.dumps({"file_id": "F2", "stage": "PD", "source_relative_path": "a.pdf"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="object_id"):
        load_files_index(tmp_path / "nested")


def test_matrix_gold_is_six_tyumen_rows() -> None:
    checks = matrix_gold_checks()
    assert len(checks) == 6
    assert {str(row["parameter_code"]) for row in checks} == {"IOS4-078", "IOS4-079"}
    assert all(row["object_id"] == "OBJ-TYUMENSKAYA-5-GOLD-SEED" for row in checks)
    assert all(row["score_eligible"] is True for row in checks)
    assert [str(row["parameter_code"]) for row in checks].count("IOS4-078") == 5


def test_duplicate_ios4_rows_share_one_finding() -> None:
    checks = matrix_gold_checks()
    hits = {"OBJ-TYUMENSKAYA-5-GOLD-SEED": {"IOS4-078"}}
    rows = score_gold_rows(hits, checks)
    assert len(rows) == 6
    ios4 = [row for row in rows if row.rule_code == "IOS4-078"]
    assert len(ios4) == 5
    assert all(row.predicted_positive for row in ios4)
    assert rows[0].rule_code == "IOS4-079"
    assert rows[0].predicted_positive is False


def test_six_of_six_does_not_meet_tz_or_close_gate_j() -> None:
    checks = matrix_gold_checks()
    hits = {"OBJ-TYUMENSKAYA-5-GOLD-SEED": {"IOS4-078", "IOS4-079"}}
    rows = score_gold_rows(hits, checks)
    report = build_report(
        RunStats(
            n_index=203,
            n_read=191,
            n_skip_stage=11,
            n_skip_missing=1,
            n_skip_excluded=0,
            n_skip_overlay=0,
            n_objects_scored=2,
            stages_by_object=(("OBJ-TYUMENSKAYA-5-GOLD-SEED", ("PD",)),),
        ),
        rows,
    )
    assert report["hits"] == 6
    assert report["recall_n"] == 6
    assert report["recall_meets_tz"] is False
    assert report["closes_gate_j"] is False
    assert report["gap_ios4_val_open"] is True
    assert report["train_public_not_frozen_val"] is True
    assert report["gold_finding_status"] == {}
    assert not recall_meets_tz(wilson(6, 6))


def test_perfect_sixteen_on_train_public_still_does_not_close_gate_j() -> None:
    rows = tuple(
        FrozenValRow(
            object_id=f"OBJ-{index:02d}",
            rule_code="IOS4-078",
            gold_positive=True,
            predicted_positive=True,
        )
        for index in range(16)
    )
    report = build_report(
        RunStats(
            n_index=0,
            n_read=0,
            n_skip_stage=0,
            n_skip_missing=0,
            n_skip_excluded=0,
            n_skip_overlay=0,
            n_objects_scored=0,
            stages_by_object=(),
        ),
        rows,
    )
    assert report["recall_meets_tz"] is True
    assert report["closes_gate_j"] is False
    assert report["train_public_not_frozen_val"] is True


def test_pred_jsonl_is_loadable_by_frozen_val(tmp_path: Path) -> None:
    checks = matrix_gold_checks()
    rows = score_gold_rows({}, checks)
    path = tmp_path / "train_public_pred.jsonl"
    lines = [
        json.dumps(pred_payload(row, check_id=str(check["check_id"])), ensure_ascii=False)
        for row, check in zip(rows, checks, strict=True)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    loaded = load_frozen_val_jsonl(path)
    assert len(loaded) == 6
    assert all(item.object_id == "OBJ-TYUMENSKAYA-5-GOLD-SEED" for item in loaded)
    assert all(item.gold_positive and not item.predicted_positive for item in loaded)


def test_select_skips_mixed_and_prefers_source_not_overlay(tmp_path: Path) -> None:
    files_root = tmp_path / "files"
    dok = files_root / "01_ПАКЕТ" / "01_ДОКУМЕНТАЦИЯ"
    dok.mkdir(parents=True)
    source = dok / "Документация" / "a.pdf"
    source.parent.mkdir()
    source.write_bytes(ascii_pdf("CODE 12345-PZ"))
    overlay = dok / "annotated_documents" / "F0001.pdf"
    overlay.parent.mkdir()
    overlay.write_bytes(b"%PDF-overlay")
    index = (
        _row(file_id="F-mix", stage="RD_ID_MIXED", source="Документация/a.pdf"),
        _row(file_id="F-pd", stage="PD", source="Документация/a.pdf"),
        _row(
            file_id="F-ov",
            stage="PD",
            source="annotated_documents/F0001.pdf",
        ),
        _row(file_id="F-miss", stage="ID", source="Документация/нет.pdf"),
    )
    blobs, stats = select_object_blobs(index, files_root, excluded=frozenset({"F0149"}))
    assert stats.n_skip_stage == 1
    assert stats.n_skip_overlay == 1
    assert stats.n_skip_missing == 1
    assert stats.n_read == 1
    novo = blobs["OBJ-NOVOSLOBODSKAYA"]
    assert len(novo) == 1
    assert novo[0][0].doc_stage is DocStage.PD
    assert novo[0][0].file_id == "F-pd"


def test_resolve_source_pdf_does_not_use_overlay(tmp_path: Path) -> None:
    files_root = tmp_path / "files"
    dok = files_root / "01_ПАКЕТ" / "01_ДОКУМЕНТАЦИЯ"
    dok.mkdir(parents=True)
    source = dok / "Документация" / "a.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-1.4 source")
    found = resolve_source_pdf(files_root, "Документация/a.pdf")
    assert found == source
    assert resolve_source_pdf(files_root, "annotated_documents/F0001.pdf") is None


def test_run_object_does_not_emit_human_verdicts() -> None:
    data = ascii_pdf("CODE 12345-PZ Rev 2 Sheet 1")
    item = PipelineFile(
        file_id="f-pd",
        file_hash="a" * 64,
        filename="pz.pdf",
        doc_stage=DocStage.PD,
    )
    findings = run_object_files(((item, data),), object_id="OBJ-NOVOSLOBODSKAYA")
    assert findings
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        item.finding_status for item in findings
    }
    codes = collect_candidates(findings)
    assert "FREE-HEATING-001" not in codes


def test_gold_mixed_loads_as_rd_not_id() -> None:
    assert loaded_stage_for_gold("PD", "PD") is DocStage.PD
    assert loaded_stage_for_gold("RD_ID_MIXED", "RD") is DocStage.RD
    with pytest.raises(ValueError, match="только как RD"):
        loaded_stage_for_gold("RD_ID_MIXED", "ID")
    with pytest.raises(ValueError, match="только как RD"):
        loaded_stage_for_gold("RD_ID_MIXED", "PD")


def test_committed_gold_evidence_keeps_gate_j_open() -> None:
    rows = load_gold_evidence_files()
    by_id = {row.file_id: row for row in rows}
    assert by_id["F0171"].loaded_as is DocStage.PD
    assert by_id["F0201"].loaded_as is DocStage.RD
    assert by_id["F0201"].stage_raw == "RD_ID_MIXED"
    assert "IOS4-078" in by_id["F0201"].matrix_codes
    assert by_id["F0202"].matrix_codes == ()
    assert all(row.object_id == "OBJ-TYUMENSKAYA-5-GOLD-SEED" for row in rows)


def test_select_gold_evidence_reads_mixed_as_rd(tmp_path: Path) -> None:
    files_root = tmp_path / "files"
    dok = files_root / "01_ПАКЕТ" / "01_ДОКУМЕНТАЦИЯ"
    dok.mkdir(parents=True)
    pd_path = dok / "Документация" / "pd.pdf"
    rd_path = dok / "Документация" / "mixed.pdf"
    pd_path.parent.mkdir()
    pd_path.write_bytes(ascii_pdf("PD"))
    rd_path.write_bytes(ascii_pdf("RD"))
    index = (
        _row(
            file_id="F0171",
            object_id="OBJ-TYUMENSKAYA-5-GOLD-SEED",
            stage="PD",
            source="Документация/pd.pdf",
        ),
        _row(
            file_id="F0201",
            object_id="OBJ-TYUMENSKAYA-5-GOLD-SEED",
            stage="RD_ID_MIXED",
            source="Документация/mixed.pdf",
        ),
        _row(
            file_id="F-other",
            object_id="OBJ-TYUMENSKAYA-5-GOLD-SEED",
            stage="RD_ID_MIXED",
            source="Документация/mixed.pdf",
        ),
    )
    evidence = (
        GoldEvidenceFile(
            file_id="F0171",
            object_id="OBJ-TYUMENSKAYA-5-GOLD-SEED",
            stage_raw="PD",
            loaded_as=DocStage.PD,
            matrix_codes=("IOS4-078",),
        ),
        GoldEvidenceFile(
            file_id="F0201",
            object_id="OBJ-TYUMENSKAYA-5-GOLD-SEED",
            stage_raw="RD_ID_MIXED",
            loaded_as=DocStage.RD,
            matrix_codes=("IOS4-078",),
        ),
    )
    blobs = select_gold_evidence_blobs(index, files_root, evidence)
    tyumen = blobs["OBJ-TYUMENSKAYA-5-GOLD-SEED"]
    stages = {item.doc_stage: item.file_id for item, _data in tyumen}
    assert stages[DocStage.PD] == "F0171"
    assert stages[DocStage.RD] == "F0201"
    assert DocStage.ID not in stages
    skipped, stats = select_object_blobs(index, files_root, excluded=frozenset())
    assert stats.n_skip_stage == 2
    assert skipped["OBJ-TYUMENSKAYA-5-GOLD-SEED"][0][0].file_id == "F0171"
