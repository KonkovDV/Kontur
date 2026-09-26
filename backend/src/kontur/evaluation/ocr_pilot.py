"""Замер Character Accuracy на OCR-пилоте. SILVER ≠ GOLD, гейт I не закрывается.

Корпус: `ocr_pilot_20260811` (zip). Речников (`OBJ-RECHNIKOV-7-7`) и карантин
скрытого теста не читаются. Эталон — `PDF_TEXT_LAYER`, не предразметка
Tesseract (иначе CA циклическая). `approved_for_training=false` у всех 300
страниц: нижняя граница Wilson здесь — инженерный отчёт, не приёмка ТЗ.

Opt-in: `KONTUR_OCR_PILOT_PATH`. Без пути pytest skip, цифры не публикуются.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from kontur.evaluation.dataset_package import is_hidden_test_object
from kontur.evaluation.inventory import QuarantineViolation, require_path_open
from kontur.evaluation.metrics import (
    TZ_THRESHOLDS,
    Interval,
    character_accuracy,
    meets_threshold,
    wilson,
)
from kontur.infrastructure.ocr_bakeoff import CA_GATE_I_THRESHOLD

OCR_PILOT_ENV = "KONTUR_OCR_PILOT_PATH"
OCR_PILOT_OUT_ENV = "KONTUR_OCR_PILOT_OUT"
OCR_PILOT_WORKERS_ENV = "KONTUR_OCR_PILOT_WORKERS"
KONTUR_ROOT_ENV = "KONTUR_ROOT"
PDF_TEXT_LAYER = "PDF_TEXT_LAYER"
RECOGNITION_LINES = "data/recognition_lines.jsonl"


@dataclass(frozen=True, slots=True)
class OcrPilotLine:
    line_id: str
    page_id: str
    object_id: str
    reference: str
    crop_path: str
    source_provenance: str


def resolve_pilot_path(env: Mapping[str, str] | None = None) -> Path | None:
    """Путь к zip/каталогу пилота или None. Карантин — исключение."""

    raw = (env or os.environ).get(OCR_PILOT_ENV)
    if not raw or not raw.strip():
        return None
    return require_path_open(Path(raw))


def discover_pilot_zip(root: Path) -> Path | None:
    """Ищет zip пилота в files/ поставки. Не открывает TEST_HIDDEN."""

    matches = sorted(root.glob("files/02_*/ocr_pilot_20260811/*.zip"))
    open_matches = [path for path in matches if not _is_blocked(path)]
    if len(open_matches) != 1:
        return None
    return require_path_open(open_matches[0])


def find_pilot_zip() -> Path | None:
    """Путь из env, затем KONTUR_ROOT/cwd/репозиторий (Docker: /app)."""

    found = resolve_pilot_path()
    if found is not None:
        return found
    roots: list[Path] = []
    raw_root = os.environ.get(KONTUR_ROOT_ENV)
    if raw_root and raw_root.strip():
        roots.append(Path(raw_root))
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
        match = discover_pilot_zip(resolved)
        if match is not None:
            return match
    return None


def eligible_for_ca(line: OcrPilotLine) -> bool:
    """Строки, на которых честно мерить OCR: не скрытый объект, не Tesseract-self."""

    if is_hidden_test_object(line.object_id):
        return False
    if line.source_provenance != PDF_TEXT_LAYER:
        return False
    if not line.crop_path.strip() or not line.reference.strip():
        return False
    return True


def load_recognition_lines(path: Path) -> tuple[OcrPilotLine, ...]:
    """Читает recognition_lines.jsonl из zip или каталога. Карантин — отказ."""

    target = require_path_open(path)
    if target.suffix.lower() == ".zip":
        return _from_zip(target)
    jsonl = target / RECOGNITION_LINES
    if not jsonl.is_file():
        nested = list(target.glob("*/data/recognition_lines.jsonl"))
        if len(nested) != 1:
            raise ValueError(f"{target}: нет {RECOGNITION_LINES}")
        jsonl = nested[0]
    require_path_open(jsonl)
    return _parse_jsonl(jsonl.read_text(encoding="utf-8"))


def accuracy_interval(
    pairs: Sequence[tuple[str, str]],
    *,
    pass_at: float | None = None,
) -> Interval:
    """Доля строк с CA ≥ pass_at. Пустая выборка порог не подтверждает."""

    threshold = TZ_THRESHOLDS["character_accuracy"] if pass_at is None else pass_at
    successes = 0
    for reference, hypothesis in pairs:
        if character_accuracy(reference, hypothesis) >= threshold:
            successes += 1
    return wilson(successes, len(pairs))


def gate_i_interval(pairs: Sequence[tuple[str, str]]) -> Interval:
    """Тот же замер с порогом bake-off 0.97. Не закрывает гейт без GOLD."""

    return accuracy_interval(pairs, pass_at=CA_GATE_I_THRESHOLD)


def tz_character_accuracy_met(interval: Interval) -> bool:
    return meets_threshold("character_accuracy", interval)


def score_crop_bytes(
    lines: Sequence[OcrPilotLine],
    crops: Mapping[str, bytes],
    ocr: Callable[[bytes], str],
    *,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[tuple[str, str], ...]:
    """(reference, hypothesis) только по eligible строкам, для которых есть crop."""

    jobs: list[tuple[str, bytes]] = []
    for line in lines:
        if not eligible_for_ca(line):
            continue
        payload = crops.get(line.crop_path)
        if payload is None:
            continue
        jobs.append((line.reference, payload))
    total = len(jobs)
    if total == 0:
        return ()
    if workers <= 1:
        pairs: list[tuple[str, str]] = []
        for index, (reference, payload) in enumerate(jobs, start=1):
            pairs.append((reference, ocr(payload)))
            if progress is not None:
                progress(index, total)
        return tuple(pairs)
    ordered: list[tuple[str, str]] = [("", "")] * total
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(ocr, payload): index for index, (_ref, payload) in enumerate(jobs)}
        for future in as_completed(pending):
            index = pending[future]
            ordered[index] = (jobs[index][0], future.result())
            done += 1
            if progress is not None:
                progress(done, total)
    return tuple(ordered)


def load_crop_bytes(path: Path, lines: Sequence[OcrPilotLine]) -> dict[str, bytes]:
    """Байты crop PNG/JPG из zip. Каталог пилота без zip не обязателен."""

    target = require_path_open(path)
    wanted = {line.crop_path for line in lines if eligible_for_ca(line)}
    if target.suffix.lower() != ".zip":
        return {}
    out: dict[str, bytes] = {}
    with ZipFile(target) as archive:
        prefix = _zip_prefix(archive.namelist())
        for crop_path in wanted:
            name = f"{prefix}/{crop_path}" if prefix else crop_path
            try:
                out[crop_path] = archive.read(name)
            except KeyError:
                continue
    return out


def _is_blocked(path: Path) -> bool:
    try:
        require_path_open(path)
    except QuarantineViolation:
        return True
    return False


def _zip_prefix(names: Sequence[str]) -> str:
    if not names:
        return ""
    first = names[0]
    if "/" not in first and "\\" not in first:
        return ""
    return first.replace("\\", "/").split("/")[0]


def _from_zip(path: Path) -> tuple[OcrPilotLine, ...]:
    with ZipFile(path) as archive:
        prefix = _zip_prefix(archive.namelist())
        name = f"{prefix}/{RECOGNITION_LINES}" if prefix else RECOGNITION_LINES
        raw = archive.read(name).decode("utf-8")
    return _parse_jsonl(raw)


def _parse_jsonl(raw: str) -> tuple[OcrPilotLine, ...]:
    rows: list[OcrPilotLine] = []
    for index, line in enumerate(raw.splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"recognition_lines:{index}: ожидался объект")
        object_id = str(payload.get("object_id") or "").strip()
        if not object_id:
            raise ValueError(f"recognition_lines:{index}: нет object_id")
        rows.append(
            OcrPilotLine(
                line_id=str(payload.get("line_id") or ""),
                page_id=str(payload.get("page_id") or ""),
                object_id=object_id,
                reference=str(payload.get("text_raw") or ""),
                crop_path=str(payload.get("crop_path") or "").replace("\\", "/"),
                source_provenance=str(payload.get("source_provenance") or ""),
            )
        )
    return tuple(rows)


def main() -> int:
    """CLI: замер на пилоте. Не печатает «гейт закрыт»."""

    from kontur.infrastructure.ocr_tesseract import (
        image_bytes_have_stamp,
        ocr_image_bytes,
        tesseract_available,
    )

    path = find_pilot_zip()
    if path is None:
        print(f"нет корпуса: задайте {OCR_PILOT_ENV} или zip в files/02_*/ocr_pilot_20260811/")
        return 2
    if not tesseract_available():
        print("tesseract/pytesseract нет; замер не выполнялся, гейт I открыт")
        return 3
    workers_raw = os.environ.get(OCR_PILOT_WORKERS_ENV, "4")
    try:
        workers = max(1, int(workers_raw))
    except ValueError:
        workers = 4

    def _progress(done: int, total: int) -> None:
        if done == total or done % 50 == 0:
            print(f"ocr-pilot {done}/{total}", file=sys.stderr, flush=True)

    lines = load_recognition_lines(path)
    crops = load_crop_bytes(path, lines)
    readable: dict[str, bytes] = {}
    n_stamp = 0
    for line in lines:
        if not eligible_for_ca(line):
            continue
        payload = crops.get(line.crop_path)
        if payload is None:
            continue
        if image_bytes_have_stamp(payload):
            n_stamp += 1
            continue
        readable[line.crop_path] = payload
    eligible_n = len(readable) + n_stamp
    coverage = (len(readable) / eligible_n) if eligible_n else 0.0
    print(
        f"ocr-pilot crops={len(crops)} readable={len(readable)} "
        f"stamp_excluded={n_stamp} workers={workers}",
        file=sys.stderr,
        flush=True,
    )
    pairs = score_crop_bytes(lines, readable, ocr_image_bytes, workers=workers, progress=_progress)
    tz = accuracy_interval(pairs)
    gate_i = gate_i_interval(pairs)
    accuracies = [character_accuracy(reference, hypothesis) for reference, hypothesis in pairs]
    mean_ca = sum(accuracies) / len(accuracies) if accuracies else 0.0
    report = {
        "pilot_path": str(path),
        "n_pairs": len(pairs),
        "n_crops": len(crops),
        "n_stamp_excluded": n_stamp,
        "coverage": coverage,
        "workers": workers,
        "mean_ca": mean_ca,
        "tz_point": tz.point,
        "tz_low": tz.low,
        "tz_high": tz.high,
        "tz_n": tz.n,
        "tz_met": tz_character_accuracy_met(tz),
        "gate_i_point": gate_i.point,
        "gate_i_low": gate_i.low,
        "gate_i_n": gate_i.n,
        "silver_not_gold": True,
        "closes_gate_i": False,
        "note": (
            "SILVER PDF_TEXT_LAYER, без Речникова. Толстое чёрное кольцо "
            "не входит в знаменатель. Не порог ТЗ. Гейт I открыт."
        ),
    }
    out_raw = os.environ.get(OCR_PILOT_OUT_ENV, "").strip()
    out_dir = Path(out_raw) if out_raw else Path.cwd() / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ocr_pilot_ca.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
