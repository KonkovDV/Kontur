"""Прогон TRAIN_PUBLIC через пайплайн. Не закрывает гейт J.

203 файла открытого train, JSONL с `object_id`. Матричный gold Тюменской —
6 позитивов; Wilson 6/6 ниже порога ТЗ. FREE-SEARCH и TEST_HIDDEN не входят.
Модель страниц как в проде: последний файл стадии. `RD_ID_MIXED` / `UNKNOWN`
не угадываем. Opt-in: без пути к пакету замер не выполняется.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kontur.application.process_pipeline import PipelineFile, run_process_pipeline
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage, Finding
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.evaluation.dataset_package import (
    LABELED_TRAIN_OBJECT_IDS,
    is_hidden_test_object,
    load_gold_inventory,
    require_labeled_train_object,
)
from kontur.evaluation.frozen_val import FrozenValRow, critical_recall, recall_meets_tz
from kontur.evaluation.inventory import is_quarantined, require_path_open

TRAIN_PUBLIC_ENV = "KONTUR_TRAIN_PUBLIC_PATH"
TRAIN_PUBLIC_OUT_ENV = "KONTUR_TRAIN_PUBLIC_OUT"
KONTUR_ROOT_ENV = "KONTUR_ROOT"
FILES_INDEX = "data/files_index.jsonl"
STAGE_PAGE_MODEL = "last_file_per_stage"
_RECHNIKOV = "речников"
_OVERLAY_DIR = "annotated_documents"


@dataclass(frozen=True, slots=True)
class TrainPublicFile:
    file_id: str
    object_id: str
    stage_raw: str
    source_relative_path: str
    output_pdf: str


@dataclass(frozen=True, slots=True)
class RunStats:
    n_index: int
    n_read: int
    n_skip_stage: int
    n_skip_missing: int
    n_skip_excluded: int
    n_skip_overlay: int
    n_objects_scored: int
    stages_by_object: tuple[tuple[str, tuple[str, ...]], ...]


def parse_doc_stage(raw: str) -> DocStage | None:
    """PD/RD/ID. MIXED и UNKNOWN не угадываем."""

    try:
        return DocStage(raw.strip())
    except ValueError:
        return None


def is_overlay_relative(relative: str) -> bool:
    """Overlay с визуальной разметкой — не источник для скоринга."""

    return _OVERLAY_DIR in relative.replace("\\", "/").casefold()


def is_predicted_positive(status: FindingStatus) -> bool:
    """Автомат: CANDIDATE. Не CONFIRMED_VIOLATION и не quality-статусы."""

    return status is FindingStatus.CANDIDATE


def load_run_inventory() -> dict[str, object]:
    """gold_inventory: репозиторий или /app/data/dataset в Docker."""

    env_root = os.environ.get(KONTUR_ROOT_ENV, "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root) / "data" / "dataset" / "gold_inventory.json")
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "data" / "dataset" / "gold_inventory.json")
    for path in candidates:
        if path.is_file() and not is_quarantined(path):
            return load_gold_inventory(path)
    return load_gold_inventory()


def excluded_file_ids(inventory: Mapping[str, object] | None = None) -> frozenset[str]:
    """F0149 дубль, F0418 битый PDF. Вне корпуса."""

    payload = inventory if inventory is not None else load_run_inventory()
    split = payload["organizer_split"]
    if not isinstance(split, dict):
        raise TypeError("organizer_split")
    raw = split.get("excluded_file_ids")
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(item) for item in raw)


def matrix_gold_checks(
    inventory: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    """6 матричных VIOLATION_PRESENT. Не FREE-SEARCH, не NO_VIOLATION."""

    payload = inventory if inventory is not None else load_run_inventory()
    checks = payload["public_gold_checks"]
    if not isinstance(checks, dict):
        raise TypeError("public_gold_checks")
    rows = checks["rows"]
    if not isinstance(rows, list):
        raise TypeError("public_gold_checks.rows")
    out: list[dict[str, object]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise TypeError("gold row")
        if raw.get("score_eligible") is not True:
            continue
        if raw.get("matrix_scope") != "MATRIX":
            continue
        if raw.get("violation_label") != "VIOLATION_PRESENT":
            continue
        object_id = str(raw.get("object_id") or "")
        require_labeled_train_object(object_id)
        out.append(raw)
    return tuple(out)


def load_files_index(package_root: Path) -> tuple[TrainPublicFile, ...]:
    """Индекс 203 файлов. Скрытый объект пропускаем. Карантинный путь — отказ."""

    root = require_path_open(package_root)
    jsonl = root / FILES_INDEX
    if not jsonl.is_file():
        nested = [path for path in root.glob(f"*/{FILES_INDEX}") if not is_quarantined(path)]
        if len(nested) != 1:
            raise ValueError(f"{root}: нет {FILES_INDEX}")
        jsonl = nested[0]
    require_path_open(jsonl)
    rows: list[TrainPublicFile] = []
    for index, line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"files_index:{index}: ожидался объект")
        object_id = str(payload.get("object_id") or "").strip()
        if not object_id:
            raise ValueError(f"files_index:{index}: нет object_id")
        if is_hidden_test_object(object_id):
            continue
        require_labeled_train_object(object_id)
        rows.append(
            TrainPublicFile(
                file_id=str(payload.get("file_id") or ""),
                object_id=object_id,
                stage_raw=str(payload.get("stage") or ""),
                source_relative_path=str(payload.get("source_relative_path") or "").replace(
                    "\\", "/"
                ),
                output_pdf=str(payload.get("output_pdf") or "").replace("\\", "/"),
            )
        )
    return tuple(rows)


def resolve_train_public_path(env: Mapping[str, str] | None = None) -> Path | None:
    """Путь к пакету или None. Карантин — исключение."""

    raw = (env or os.environ).get(TRAIN_PUBLIC_ENV)
    if not raw or not raw.strip():
        return None
    return require_path_open(Path(raw))


def discover_train_public_root(root: Path) -> Path | None:
    """Каталог распакованного TRAIN_PUBLIC в files/. Не TEST_HIDDEN."""

    files_dir = root / "files"
    if not files_dir.is_dir():
        return None
    matches = sorted(
        path
        for path in files_dir.iterdir()
        if path.is_dir() and "TRAIN_PUBLIC" in path.name and not is_quarantined(path)
    )
    if len(matches) != 1:
        return None
    return require_path_open(matches[0])


def find_train_public_root() -> Path | None:
    found = resolve_train_public_path()
    if found is not None:
        return found
    roots: list[Path] = []
    env_root = os.environ.get(KONTUR_ROOT_ENV, "").strip()
    if env_root:
        roots.append(Path(env_root))
    roots.append(Path.cwd())
    here = Path(__file__).resolve()
    if len(here.parents) >= 5:
        roots.append(here.parents[4])
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        match = discover_train_public_root(resolved)
        if match is not None:
            return match
    return None


def resolve_files_root(package: Path, env: Mapping[str, str] | None = None) -> Path:
    """Каталог files/: исходные PDF рядом с пакетом разметки."""

    if package.parent.name == "files":
        return package.parent
    environ = env if env is not None else os.environ
    raw = environ.get(KONTUR_ROOT_ENV, "").strip()
    if raw:
        candidate = Path(raw) / "files"
        if candidate.is_dir():
            return candidate
    cwd_files = Path.cwd() / "files"
    if cwd_files.is_dir():
        return cwd_files
    return package.parent


def resolve_source_pdf(files_root: Path, relative: str) -> Path | None:
    """Исходный PDF в открытой документации. Не overlay, не Речников."""

    if not relative.strip() or is_overlay_relative(relative):
        return None
    rel = Path(relative.replace("\\", "/"))
    pkg = next(
        (
            path
            for path in files_root.iterdir()
            if path.is_dir() and path.name.startswith("01_") and not _walk_blocked(path)
        ),
        None,
    )
    if pkg is None:
        return None
    for base in _dokumentatsia_dirs(pkg):
        candidate = base / rel
        if candidate.is_file() and not _walk_blocked(candidate):
            return require_path_open(candidate)
    return None


def collect_candidates(findings: Sequence[Finding]) -> set[str]:
    return {item.rule_code for item in findings if is_predicted_positive(item.finding_status)}


def score_gold_rows(
    candidates: Mapping[str, set[str]],
    checks: Sequence[Mapping[str, object]],
) -> tuple[FrozenValRow, ...]:
    """Одна строка на публичную матричную проверку. Дубли IOS4-078 сохраняем."""

    rows: list[FrozenValRow] = []
    for check in checks:
        object_id = str(check["object_id"])
        rule_code = str(check["parameter_code"])
        hit = rule_code in candidates.get(object_id, set())
        rows.append(
            FrozenValRow(
                object_id=object_id,
                rule_code=rule_code,
                gold_positive=True,
                predicted_positive=hit,
            )
        )
    return tuple(rows)


def pred_payload(row: FrozenValRow, *, check_id: str = "") -> dict[str, object]:
    payload: dict[str, object] = {
        "object_id": row.object_id,
        "rule_code": row.rule_code,
        "gold_positive": row.gold_positive,
        "predicted_positive": row.predicted_positive,
    }
    if check_id:
        payload["check_id"] = check_id
    return payload


def build_report(
    stats: RunStats,
    gold_rows: Sequence[FrozenValRow],
) -> dict[str, object]:
    """Всегда closes_gate_j=false: TRAIN_PUBLIC ≠ frozen val."""

    interval = critical_recall(
        [row.gold_positive for row in gold_rows],
        [row.predicted_positive for row in gold_rows],
    )
    return {
        "n_index": stats.n_index,
        "n_read": stats.n_read,
        "n_skip_stage": stats.n_skip_stage,
        "n_skip_missing": stats.n_skip_missing,
        "n_skip_excluded": stats.n_skip_excluded,
        "n_skip_overlay": stats.n_skip_overlay,
        "n_objects_scored": stats.n_objects_scored,
        "stages_by_object": {key: list(value) for key, value in stats.stages_by_object},
        "stage_page_model": STAGE_PAGE_MODEL,
        "n_gold_matrix": len(gold_rows),
        "hits": sum(1 for row in gold_rows if row.predicted_positive),
        "recall_point": interval.point,
        "recall_low": interval.low,
        "recall_n": interval.n,
        "recall_meets_tz": recall_meets_tz(interval),
        "closes_gate_j": False,
        "gap_ios4_val_open": True,
        "train_public_not_frozen_val": True,
        "note": "6 матричных позитивов TRAIN_PUBLIC. Не публиковать как порог ТЗ.",
    }


def run_object_files(
    items: Sequence[tuple[PipelineFile, bytes]],
    *,
    object_id: str,
) -> tuple[Finding, ...]:
    """Один объект. Последний файл стадии побеждает, как в HTTP-пайплайне."""

    require_labeled_train_object(object_id)
    if not items:
        return ()
    completeness: CompletenessMap = {
        DocStage.PD: Completeness.MISSING,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    files: list[PipelineFile] = []
    blobs: dict[str, bytes] = {}
    for item, data in items:
        completeness[item.doc_stage] = Completeness.UPLOADED
        files.append(item)
        blobs[item.file_id] = data
    report = run_process_pipeline(
        object_id=object_id,
        completeness=completeness,
        files=tuple(files),
        blobs=blobs,
    )
    return report.findings


def select_object_blobs(
    index: Sequence[TrainPublicFile],
    files_root: Path,
    *,
    excluded: frozenset[str],
) -> tuple[dict[str, list[tuple[PipelineFile, bytes]]], RunStats]:
    """Читает исходные PDF. В оценку — последний файл каждой стадии."""

    last: dict[str, dict[DocStage, tuple[PipelineFile, bytes]]] = {}
    n_read = 0
    n_skip_stage = 0
    n_skip_missing = 0
    n_skip_excluded = 0
    n_skip_overlay = 0
    for item in index:
        if item.file_id in excluded:
            n_skip_excluded += 1
            continue
        if is_overlay_relative(item.source_relative_path):
            n_skip_overlay += 1
            continue
        stage = parse_doc_stage(item.stage_raw)
        if stage is None:
            n_skip_stage += 1
            continue
        source = resolve_source_pdf(files_root, item.source_relative_path)
        if source is None:
            n_skip_missing += 1
            continue
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        pipe = PipelineFile(
            file_id=item.file_id,
            file_hash=digest,
            filename=source.name,
            doc_stage=stage,
        )
        last.setdefault(item.object_id, {})[stage] = (pipe, data)
        n_read += 1

    blobs: dict[str, list[tuple[PipelineFile, bytes]]] = {}
    stages_by_object: list[tuple[str, tuple[str, ...]]] = []
    for object_id in sorted(LABELED_TRAIN_OBJECT_IDS):
        by_stage = last.get(object_id, {})
        ordered = [by_stage[stage] for stage in DocStage if stage in by_stage]
        blobs[object_id] = ordered
        stages_by_object.append(
            (object_id, tuple(stage.value for stage in DocStage if stage in by_stage))
        )
    stats = RunStats(
        n_index=len(index),
        n_read=n_read,
        n_skip_stage=n_skip_stage,
        n_skip_missing=n_skip_missing,
        n_skip_excluded=n_skip_excluded,
        n_skip_overlay=n_skip_overlay,
        n_objects_scored=sum(1 for items in blobs.values() if items),
        stages_by_object=tuple(stages_by_object),
    )
    return blobs, stats


def run_package(
    package: Path,
    files_root: Path,
) -> tuple[tuple[FrozenValRow, ...], dict[str, object]]:
    """Индекс → исходные PDF → пайплайн по объекту → JSONL-совместимые строки."""

    inventory = load_run_inventory()
    index = load_files_index(package)
    checks = matrix_gold_checks(inventory)
    excluded = excluded_file_ids(inventory)
    blobs, stats = select_object_blobs(index, files_root, excluded=excluded)
    by_object: dict[str, set[str]] = {object_id: set() for object_id in LABELED_TRAIN_OBJECT_IDS}
    for object_id, items in blobs.items():
        if not items:
            continue
        print(f"train-public object={object_id} files={len(items)}", file=sys.stderr, flush=True)
        findings = run_object_files(items, object_id=object_id)
        by_object[object_id] = collect_candidates(findings)
    gold_rows = score_gold_rows(by_object, checks)
    return gold_rows, build_report(stats, gold_rows)


def _walk_blocked(path: Path) -> bool:
    if is_quarantined(path):
        return True
    text = path.name.casefold()
    return _RECHNIKOV in text or "rechnikov" in text


def _dokumentatsia_dirs(package: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(package):
        current = Path(dirpath)
        if _walk_blocked(current):
            dirnames.clear()
            continue
        dirnames[:] = [name for name in dirnames if not _walk_blocked(current / name)]
        name = current.name.casefold()
        if name.startswith("01_") and "документация" in name:
            found.append(current)
    return tuple(found)


def main() -> int:
    """CLI. Всегда пишет closes_gate_j=false. Не печатает «гейт закрыт»."""

    package = find_train_public_root()
    if package is None:
        print(f"нет корпуса: задайте {TRAIN_PUBLIC_ENV} или files/*TRAIN_PUBLIC*")
        return 2
    files_root = resolve_files_root(package)
    gold_rows, report = run_package(package, files_root)
    checks = matrix_gold_checks()
    out_raw = os.environ.get(TRAIN_PUBLIC_OUT_ENV, "").strip()
    out_dir = Path(out_raw) if out_raw else Path.cwd() / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "train_public_pred.jsonl"
    lines = [
        json.dumps(
            pred_payload(row, check_id=str(check.get("check_id") or "")),
            ensure_ascii=False,
        )
        for row, check in zip(gold_rows, checks, strict=True)
    ]
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    report_path = out_dir / "train_public_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {jsonl_path}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
