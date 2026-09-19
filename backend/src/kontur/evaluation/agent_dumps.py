"""Снимки для следующего агента. Не scorecard ТЗ, не содержимое TEST_HIDDEN."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from kontur.evaluation.dataset_package import (
    HIDDEN_TEST_OBJECT_IDS,
    LABELED_TRAIN_OBJECT_IDS,
    load_gold_inventory,
)
from kontur.infrastructure.matrix.registry import KNOWN_COVERAGE, FileRuleRegistry

SCHEMA_VERSION = "1.0.0"


def repo_root() -> Path:
    """Корень репозитория: есть data/dataset/gold_inventory.json."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "dataset" / "gold_inventory.json").is_file():
            return parent
    return here.parents[4]


def coverage_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "matrix" / "coverage_snapshot.json"


def handoff_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "dataset" / "agent_handoff.json"


def index_stats_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "dataset" / "train_public_index_stats.json"


def git_sha(root: Path | None = None) -> str:
    """SHA HEAD без subprocess. Пустая строка, если .git недоступен."""

    git_dir = (root or repo_root()) / ".git"
    head = git_dir / "HEAD"
    if not head.is_file():
        return ""
    text = head.read_text(encoding="utf-8").strip()
    if text.startswith("ref:"):
        ref = git_dir / text.split(" ", 1)[1].strip()
        if ref.is_file():
            return ref.read_text(encoding="utf-8").strip()
        return ""
    return text


def build_coverage_snapshot(registry: FileRuleRegistry | None = None) -> dict[str, object]:
    """Разбивка coverage + списки кодов. Не «132 проверки реализованы»."""

    source = registry or FileRuleRegistry()
    codes: dict[str, list[str]] = {name: [] for name in sorted(KNOWN_COVERAGE)}
    for code in source.all_codes():
        coverage = str(source.get(code)["coverage"])
        codes.setdefault(coverage, []).append(code)
    counts = source.coverage_report()
    executable = int(counts.get("executable", 0))
    declared = int(counts.get("declared", 0))
    return {
        "schema_version": SCHEMA_VERSION,
        "matrix_version": source.matrix_version,
        "counts": counts,
        "codes": {key: sorted(value) for key, value in codes.items()},
        "gate_h_minimum_20_executable": executable >= 20,
        "executable_equals_declared": executable == declared,
        "closes_gate_j": False,
        "note": (
            "executable — рабочий экстрактор, не вся матрица и не порог ТЗ. "
            "Coverage только в разбивке snapshot, без заявления что вся матрица executable."
        ),
    }


def build_handoff(
    *,
    coverage: Mapping[str, object] | None = None,
    index_stats: Mapping[str, object] | None = None,
    root: Path | None = None,
) -> dict[str, object]:
    """Операционный пакет: гейты, запреты, команды, указатели."""

    base = root or repo_root()
    inventory = load_gold_inventory()
    cov = coverage if coverage is not None else build_coverage_snapshot()
    counts = cov["counts"]
    if not isinstance(counts, dict):
        raise TypeError("coverage.counts")
    verdict = inventory["verdict"]
    if not isinstance(verdict, dict):
        raise TypeError("gold_inventory.verdict")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_on": date.today().isoformat(),
        "export_git_sha": git_sha(base),
        "deadline": "2026-09-29T23:59:00+03:00",
        "purpose": (
            "Handoff для следующего ИИ. Не frozen val, не GOLD OCR, не scorecard ТЗ."
        ),
        "human_doc": "docs/AGENT_HANDOFF.md",
        "invariants_doc": "AGENTS.md",
        "closes_gate_i": False,
        "closes_gate_j": False,
        "closes_gate_k": False,
        "closes_gate_l": False,
        "hidden_test_contents_inspected": False,
        "allowlist_object_ids": sorted(LABELED_TRAIN_OBJECT_IDS),
        "hidden_test_object_ids": sorted(HIDDEN_TEST_OBJECT_IDS),
        "work_plan_steps": {
            "0_http_pipeline": "landed",
            "1_ocr_in_request": "code_landed_gate_i_open",
            "2_inspector_queue": "landed",
            "3_train_public": "harness_landed_run_opt_in",
            "4_gate_k_usability": "form_only_no_sessions",
            "5_gate_l_k6": "measured_on_gha_not_production_sla",
        },
        "open_gaps": [
            "GAP-CAP-OCR",
            "GAP-OCR-ROT",
            "GAP-STAMP",
            "GAP-IOS4-VAL",
            "RT-2609-21",
            "GAP-FREE-SEARCH",
            "GAP-DWG",
            "GAP-ISOLATE",
            "GAP-SPLIT",
        ],
        "coverage_counts": counts,
        "gold_matrix_positives": 6,
        "wilson_perfect_n_min_recall": 16,
        "pipeline_limitations": [
            "last_file_per_stage_fallback",
            "non_gold_RD_ID_MIXED_skipped",
            "gold_RD_ID_MIXED_loaded_as_RD_only",
            "pd_cover_without_filled_utverdil",
            "ocr_text_UNAVAILABLE",
        ],
        "do_not": [
            "Merge leftover OCR branches (PR #54, 2ddc2b3 one-line ocr_tesseract.py)",
            "Open TEST_HIDDEN / РАЗМЕЧЕННЫЙ_TEST__213 / Rechnikov for thresholds",
            "Set ocr_text AVAILABLE without GOLD Wilson",
            "Close GAP-IOS4-VAL on 15 gold rows or SILVER CA",
            "Publish P/R/F1/CA as TZ without frozen val n and 95% CI",
            "Publish GHA k6 p95 as production SLA",
            "Treat static JWT public key as production OIDC/JWKS",
            "Write CONFIRMED_VIOLATION from the automaton or LLM",
            "Guess non-gold RD_ID_MIXED as RD+ID",
            "Treat GOST Согласовано/ГИП header as approved etalon",
            "Prefer annotated_documents overlays over source PDFs",
        ],
        "commands": {
            "ci_local": "python -m pytest backend/tests -q && python scripts/check_claims.py",
            "dumps": "python scripts/export_agent_dumps.py",
            "train_public": "make train-public",
            "ocr_pilot": "make ocr-pilot",
            "dry_run_132": "python -m pytest backend/tests/test_dry_run.py -q",
        },
        "pointers": {
            "gold_inventory": "data/dataset/gold_inventory.json",
            "gold_evidence_files": "data/dataset/gold_evidence_files.json",
            "coverage_snapshot": "data/matrix/coverage_snapshot.json",
            "index_stats": "data/dataset/train_public_index_stats.json",
            "train_public_engineering": "data/dataset/train_public_engineering.json",
            "train_public_pred": "data/dataset/train_public_pred.jsonl",
            "work_plan": "docs/WORK_PLAN.md",
            "known_gaps": "docs/KNOWN_GAPS.md",
            "performance": "docs/PERFORMANCE.md",
            "gate_l_runbook": "docs/GATE_L_RUNBOOK.md",
            "pr_queue": "docs/PR_QUEUE.md",
            "organizer_gold": "docs/ORGANIZER_GOLD.md",
            "train_public_module": "backend/src/kontur/evaluation/train_public.py",
            "ocr_pilot_module": "backend/src/kontur/evaluation/ocr_pilot.py",
        },
        "leftover_refs_do_not_merge": [
            "feat/ocr-gate-i-crop3x-oem1",
            "feat/ocr-300dpi-step2-verifying",
        ],
        "index_stats_present": index_stats is not None,
        "verdict_echo": {
            "frozen_validation_corpus_for_132": verdict.get(
                "frozen_validation_corpus_for_132"
            ),
            "closes_gate_j": verdict.get("closes_gate_j"),
        },
    }


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def maybe_index_stats(root: Path | None = None) -> dict[str, object] | None:
    """Индекс TRAIN_PUBLIC, если files/ на машине. Иначе None, карантин не читаем."""

    from kontur.evaluation.train_public import (
        discover_train_public_root,
        load_files_index,
        resolve_files_root,
        summarize_index,
    )

    base = root or repo_root()
    package = discover_train_public_root(base)
    if package is None:
        return None
    files_root = resolve_files_root(package)
    return summarize_index(load_files_index(package), files_root)


def export_all(root: Path | None = None) -> dict[str, Path]:
    """Пишет JSON в data/. index_stats — только при наличии открытого train."""

    base = root or repo_root()
    coverage = build_coverage_snapshot()
    stats = maybe_index_stats(base)
    handoff = build_handoff(coverage=coverage, index_stats=stats, root=base)
    written = {
        "coverage": coverage_path(base),
        "handoff": handoff_path(base),
    }
    write_json(written["coverage"], coverage)
    write_json(written["handoff"], handoff)
    if stats is not None:
        target = index_stats_path(base)
        write_json(target, stats)
        written["index_stats"] = target
    return written
