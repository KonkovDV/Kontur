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


def scorecard_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "dataset" / "tz_scorecard.json"


def extractor_families_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data" / "matrix" / "extractor_families.json"


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
            "4_gate_k_usability": "recorder_landed_no_sessions",
            "5_gate_l_k6": "measured_on_gha_not_production_sla",
            "6_contest_vertical_slice": "inspector_etalon_landed_gates_open",
        },
        "open_gaps": [
            "GAP-CAP-OCR",
            "GAP-OCR-ROT",
            "GAP-STAMP",
            "GAP-IOS4-VAL",
            "RT-2609-21",
            "GAP-FREE-SEARCH",
            "GAP-DWG",
            "GAP-SPLIT",
        ],
        "coverage_counts": counts,
        "gold_matrix_positives": 6,
        "wilson_perfect_n_min_recall": 16,
        "pipeline_limitations": [
            "train_public_harness_still_last_file_per_stage",
            "non_gold_RD_ID_MIXED_skipped",
            "gold_RD_ID_MIXED_loaded_as_RD_only",
            "pd_cover_without_filled_utverdil",
            "ocr_text_MEASURED_below_gate",
        ],
        "do_not": [
            "Merge leftover OCR branches (PR #54, 2ddc2b3 one-line ocr_tesseract.py)",
            "Open TEST_HIDDEN / РАЗМЕЧЕННЫЙ_TEST__213 / Rechnikov for thresholds",
            "Set ocr_text AVAILABLE without GOLD Wilson",
            "Close GAP-IOS4-VAL on 15 gold rows or SILVER CA",
            "Publish P/R/F1/CA as TZ without frozen val n and 95% CI",
            "Publish GHA k6 p95 as production SLA",
            "Treat static JWT public key as production OIDC/JWKS",
            "Open ПАКЕТ_ОРГАНИЗАТОРА_ЗАКРЫТЫЙ_v2.0.zip or TEST_HIDDEN answers for thresholds",
            "Treat participant package without answers v2.0 as frozen val",
            "Treat object 10_Полярная_25_СОШ1100к7 as frozen val or matrix gold",
            "Write CONFIRMED_VIOLATION from the automaton or LLM",
            "Guess non-gold RD_ID_MIXED as RD+ID",
            "Treat GOST Согласовано/ГИП header as approved etalon",
            "Prefer annotated_documents overlays over source PDFs",
            "Revive PR #61 import-time monkeypatch of ProcessRecord",
            "Revive PR #63 experimental materialization (stripped provenance)",
            "Require kind=materialized or assembled=true on TZ protocol JSON",
            "Treat broker confirm or inbox RECEIVED as process SYNCED / Rin ACK",
            "Do not add OIDC/TLS/RabbitMQ 4.x/observability instead of contest slice",
            "Treat inspector-selected etalon as stamp evidence or close gate J",
        ],
        "commands": {
            "ci_local": "python -m pytest backend/tests -q && python scripts/check_claims.py",
            "dumps": "python scripts/export_agent_dumps.py",
            "submission_pack": "python scripts/export_submission_pack.py",
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
            "dataset_package": "docs/DATASET_PACKAGE.md",
            "questions_to_organizer": "docs/QUESTIONS_TO_ORGANIZER.md",
            "train_public_module": "backend/src/kontur/evaluation/train_public.py",
            "ocr_pilot_module": "backend/src/kontur/evaluation/ocr_pilot.py",
            "tz_scorecard": "data/dataset/tz_scorecard.json",
            "extractor_families": "data/matrix/extractor_families.json",
            "family_triage": "data/matrix/family_triage.json",
            "class_ladder_triage": "data/matrix/class_ladder_triage.json",
            "number_family_triage": "data/matrix/number_family_triage.json",
            "research_osint": "docs/RESEARCH_OSINT_2026.md",
            "extractor_family_triage": "docs/EXTRACTOR_FAMILY_TRIAGE.md",
            "class_ladder_triage_doc": "docs/CLASS_LADDER_TRIAGE.md",
            "number_family_triage_doc": "docs/NUMBER_FAMILY_TRIAGE.md",
            "gh_situation": "docs/GH_SITUATION_2026_09_21.md",
            "gh_agent_bus": "docs/GH_AGENT_BUS.md",
            "submission_pack": "docs/SUBMISSION_PACK.md",
            "adr_0009": "docs/adr/0009-atomic-protocol-materialization.md",
            "adr_0010": "docs/adr/0010-outbox-relay-to-broker.md",
            "adr_0011": "docs/adr/0011-sync-lifecycle-and-manual-retry.md",
            "adr_0012": "docs/adr/0012-transactional-inbox.md",
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


def _scorecard_item(item_id: str, state: str, detail: str) -> dict[str, str]:
    if state not in {"met", "partial", "unmet"}:
        raise ValueError(f"state {state}")
    return {"id": item_id, "state": state, "detail": detail}


def build_extractor_families(
    registry: FileRuleRegistry | None = None,
) -> dict[str, object]:
    """Группировка 132 правил по extractor.type. Не делает extractor_missing executable."""

    source = registry or FileRuleRegistry()
    families: dict[str, dict[str, list[str]]] = {}
    for code in source.all_codes():
        rule = source.get(code)
        extractor = rule.get("extractor")
        family = "unknown"
        if isinstance(extractor, dict) and extractor.get("type") is not None:
            family = str(extractor["type"])
        coverage = str(rule["coverage"])
        bucket = families.setdefault(
            family,
            {name: [] for name in sorted(KNOWN_COVERAGE)},
        )
        bucket.setdefault(coverage, []).append(code)
    codes_by_family = {
        family: {key: sorted(values) for key, values in buckets.items()}
        for family, buckets in sorted(families.items())
    }
    counts_by_family = {
        family: {key: len(values) for key, values in buckets.items()}
        for family, buckets in codes_by_family.items()
    }
    still_missing = sum(
        buckets.get("extractor_missing", 0) for buckets in counts_by_family.values()
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "matrix_version": source.matrix_version,
        "purpose": (
            "Cluster compiled rules by extractor.type. Grouping is not executable coverage."
        ),
        "closes_gate_j": False,
        "counts_by_family": counts_by_family,
        "codes_by_family": codes_by_family,
        "note": (
            f"{still_missing} extractor_missing remain missing until each family has a working "
            "extractor and fixtures. Do not treat this file as 132/132."
        ),
    }


def build_tz_scorecard(
    *,
    coverage: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Три контура готовности. Не порог ТЗ, не P/R/F1, не закрытие гейтов."""

    cov = coverage if coverage is not None else build_coverage_snapshot()
    counts = cov["counts"]
    if not isinstance(counts, dict):
        raise TypeError("coverage.counts")
    executable = int(counts.get("executable", 0))
    declared = int(counts.get("declared", 0))
    missing = int(counts.get("extractor_missing", 0))
    code_items = [
        _scorecard_item("matrix_declared_132", "met", f"declared={declared}"),
        _scorecard_item(
            "matrix_executable_132",
            "unmet",
            f"executable={executable} extractor_missing={missing}",
        ),
        _scorecard_item(
            "http_vector_pipeline",
            "partial",
            "L1-L7 upload; ocr_text MEASURED, gate I open",
        ),
        _scorecard_item(
            "protocol_atomic_materialization",
            "partial",
            "PR #64 plus lock/sha/outbox; live PG race in CI; no kind=materialized",
        ),
        _scorecard_item("rin_sandbox", "unmet", "retry policy only; no sandbox contract"),
        _scorecard_item(
            "async_rabbit_outbox_workers",
            "partial",
            "outbox+inbox workers in compose; ACK after commit; HTTP inline; not Rin",
        ),
        _scorecard_item("split_finding", "unmet", "GAP-SPLIT NotImplementedError"),
    ]
    acceptance_items = [
        _scorecard_item("gold_ocr", "unmet", "ocr_text MEASURED; SILVER is not GOLD"),
        _scorecard_item("frozen_val_132", "unmet", "no frozen val; 6 gold positives < n=16"),
        _scorecard_item("gate_i", "unmet", "GAP-CAP-OCR / GAP-IOS4-VAL open"),
        _scorecard_item("gate_j", "unmet", "closes_gate_j false"),
        _scorecard_item("gate_k", "unmet", "recorder landed; no five sessions"),
        _scorecard_item("gate_l_tz", "unmet", "GHA /status measured; not production SLA"),
    ]
    production_items = [
        _scorecard_item("jwt_rs256", "partial", "static key containment; not OIDC/JWKS"),
        _scorecard_item(
            "container_hardening",
            "partial",
            "PR #60 non-root loopback; not TLS 1.3",
        ),
        _scorecard_item("oidc_jwks", "unmet", "no rotation"),
        _scorecard_item("antivirus", "unmet", "intake MIME/zip-bomb only"),
        _scorecard_item("branch_protection", "unmet", "main unprotected"),
        _scorecard_item("observability_otel", "unmet", "no Prometheus/Grafana stack"),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_on": date.today().isoformat(),
        "purpose": (
            "Engineering completeness tracks. Not TZ acceptance and not published P/R/F1/CA."
        ),
        "closes_gate_i": False,
        "closes_gate_j": False,
        "closes_gate_k": False,
        "closes_gate_l": False,
        "not_tz_percentage": True,
        "coverage_counts": counts,
        "tracks": {
            "code": code_items,
            "acceptance": acceptance_items,
            "production": production_items,
        },
        "contest_rc": [
            "safe postgres finalize",
            "gate_k five inspectors",
            "honest coverage report",
            "no machine CONFIRMED_VIOLATION",
            "measured gate L not SLA",
        ],
        "deadline": "2026-09-29T23:59:00+03:00",
        "note": "100% TZ is unreachable without GOLD OCR, frozen val and five inspectors.",
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
    families = build_extractor_families()
    scorecard = build_tz_scorecard(coverage=coverage)
    written = {
        "coverage": coverage_path(base),
        "handoff": handoff_path(base),
        "extractor_families": extractor_families_path(base),
        "scorecard": scorecard_path(base),
    }
    write_json(written["coverage"], coverage)
    write_json(written["handoff"], handoff)
    write_json(written["extractor_families"], families)
    write_json(written["scorecard"], scorecard)
    if stats is not None:
        target = index_stats_path(base)
        write_json(target, stats)
        written["index_stats"] = target
    return written
