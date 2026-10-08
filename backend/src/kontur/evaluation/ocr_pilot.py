"""Замер OCR на пилоте. SILVER ≠ GOLD, гейт I не закрывается.

Корпус: `ocr_pilot_20260811` (zip). Речников (`OBJ-RECHNIKOV-7-7`) и карантин
скрытого теста не читаются. Эталон — `PDF_TEXT_LAYER`, не предразметка
Tesseract (иначе CA циклическая). `approved_for_training=false` у всех 300
страниц.

Character Accuracy ТЗ — микро-доля 1 − ΣЛевенштейн / Σсимволов. Доля строк
с построчным CA не ниже 0,95 — другая величина; её Уилсон публикуется рядом
и сам по себе гейт не закрывает. Оба условия плюс GOLD нужны, чтобы закрыть
гейт I. На этом корпусе `gold` ложь.

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
    LineBootstrap,
    PooledCharacterAccuracy,
    character_accuracy,
    meets_threshold,
    pooled_ca_line_bootstrap,
    pooled_character_accuracy,
    wilson,
)
from kontur.infrastructure.ocr_bakeoff import CA_GATE_I_THRESHOLD

OCR_PILOT_ENV = "KONTUR_OCR_PILOT_PATH"
OCR_PILOT_OUT_ENV = "KONTUR_OCR_PILOT_OUT"
OCR_PILOT_WORKERS_ENV = "KONTUR_OCR_PILOT_WORKERS"
OCR_PILOT_ENGINE_ENV = "KONTUR_OCR_PILOT_ENGINE"
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
    flags: tuple[str, ...] = ()
    bbox_pdf_pt: tuple[float, float, float, float] | None = None


def resolve_pilot_path(env: Mapping[str, str] | None = None) -> Path | None:
    """Путь к zip/каталогу пилота или None. Карантин — исключение."""

    source = os.environ if env is None else env
    raw = source.get(OCR_PILOT_ENV)
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
    """Нижняя граница Уилсона по доле строк. Это не микро-CA."""

    return meets_threshold("character_accuracy", interval)


def judge_recorded_ocr(interval: Interval, *, gold: bool = False) -> dict[str, object]:
    """Уилсон доли строк. SILVER при `gold=False` гейт не закрывает.

    Интервал здесь — доля строк, а не микро-CA. Для приёмки по формуле ТЗ
    нужен `judge_pooled_ocr`.
    """

    met = tz_character_accuracy_met(interval)
    return {
        "estimand": "line_pass_rate",
        "n": interval.n,
        "low": interval.low,
        "threshold": TZ_THRESHOLDS["character_accuracy"],
        "threshold_met": met,
        "gold": gold,
        "closes_gate_i": False,
    }


def _bootstrap_block(interval: LineBootstrap | None) -> dict[str, object] | None:
    if interval is None:
        return None
    return {
        "low": interval.low,
        "high": interval.high,
        "n_lines": interval.n_lines,
        "unit": "line",
        "decides_threshold": interval.decides_threshold,
    }


_OCR_FLAGS = ("VERTICAL", "STAMP", "LOW_QUALITY")


def _flag_rows(
    pairs: Sequence[tuple[str, str]],
    line_flags: Sequence[Sequence[str]] | None,
) -> list[tuple[str, ...]]:
    if line_flags is None:
        return [() for _ in pairs]
    flags = [tuple(str(item) for item in row) for row in line_flags]
    if len(flags) != len(pairs):
        raise ValueError("line_flags: число флагов не равно числу строк")
    return flags


def _flag_slice(
    pairs: Sequence[tuple[str, str]],
    flags: Sequence[tuple[str, ...]],
    name: str,
) -> dict[str, object] | None:
    subset = [pair for pair, row in zip(pairs, flags, strict=True) if name in row]
    if not subset:
        return None
    pooled = pooled_character_accuracy(subset)
    return {
        "n_lines": pooled.n_lines,
        "point": pooled.point,
        "cer": pooled.cer,
        "defined": pooled.point is not None,
    }


def character_accuracy_report(
    pairs: Sequence[tuple[str, str]],
    *,
    line_flags: Sequence[Sequence[str]] | None = None,
) -> dict[str, object]:
    """Микро-CA и рядом — доля строк. Гейт этим отчётом не закрывается.

    ``ABSTAIN`` остаётся в знаменателе CA и выходит из coverage.
    Срезы VERTICAL, STAMP и LOW_QUALITY порог не решают.
    """

    flags = _flag_rows(pairs, line_flags)
    pooled: PooledCharacterAccuracy = pooled_character_accuracy(pairs)
    line_pass = accuracy_interval(pairs)
    bootstrap = pooled_ca_line_bootstrap(pairs)
    point_meets = (
        pooled.point is not None and pooled.point >= TZ_THRESHOLDS["character_accuracy"]
    )
    line_pass_met = tz_character_accuracy_met(line_pass)
    covered = sum(1 for row in flags if "ABSTAIN" not in row)
    by_flag = {
        name: block
        for name in _OCR_FLAGS
        if (block := _flag_slice(pairs, flags, name)) is not None
    }
    return {
        "estimand": "pooled_micro",
        "formula": "1 - sum(Levenshtein) / sum(reference_chars)",
        "point": pooled.point,
        "cer": pooled.cer,
        "wer": pooled.wer,
        "line_exact_match": pooled.line_exact_match,
        "edit_distance": pooled.edit_distance,
        "ref_chars": pooled.ref_chars,
        "token_distance": pooled.token_distance,
        "ref_tokens": pooled.ref_tokens,
        "exact_lines": pooled.exact_lines,
        "n_lines": pooled.n_lines,
        "defined": pooled.point is not None,
        "threshold": TZ_THRESHOLDS["character_accuracy"],
        "point_meets_threshold": point_meets,
        "line_bootstrap_95": _bootstrap_block(bootstrap),
        "line_pass_rate": {
            "estimand": "share_of_lines_with_per_line_ca_at_least_threshold",
            "point": line_pass.point,
            "low": line_pass.low,
            "high": line_pass.high,
            "n": line_pass.n,
            "wilson_lower_meets_threshold": line_pass_met,
        },
        "coverage": (covered / len(pairs)) if pairs else None,
        "by_flag": by_flag,
        "closes_gate_i": False,
    }


def judge_pooled_ocr(
    pairs: Sequence[tuple[str, str]],
    *,
    gold: bool = False,
    line_flags: Sequence[Sequence[str]] | None = None,
) -> dict[str, object]:
    """Гейт I: микро-CA ≥ 0,95, Уилсон доли строк ≥ 0,95, и эталон — GOLD.

    Одной точки на двух символах мало. Одной доли строк мало: короткие
    верные строки прячут длинный промах, и микро-CA при этом ниже порога.
    """

    report = character_accuracy_report(pairs, line_flags=line_flags)
    line_pass = report["line_pass_rate"]
    line_pass_met = (
        isinstance(line_pass, dict)
        and line_pass.get("wilson_lower_meets_threshold") is True
    )
    closes = bool(gold and report["point_meets_threshold"] is True and line_pass_met)
    return {
        **report,
        "gold": gold,
        "silver_not_gold": not gold,
        "closes_gate_i": closes,
    }


def _crop_jobs(
    lines: Sequence[OcrPilotLine],
    crops: Mapping[str, bytes],
) -> list[tuple[str, bytes, tuple[str, ...]]]:
    jobs: list[tuple[str, bytes, tuple[str, ...]]] = []
    for line in lines:
        if not eligible_for_ca(line):
            continue
        payload = crops.get(line.crop_path)
        if payload is None:
            continue
        jobs.append((line.reference, payload, line.flags))
    return jobs


def score_crop_bytes(
    lines: Sequence[OcrPilotLine],
    crops: Mapping[str, bytes],
    ocr: Callable[[bytes], str],
    *,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[tuple[str, str], ...]:
    """(reference, hypothesis) только по eligible строкам, для которых есть crop."""

    pairs, _flags = _score_crops(lines, crops, ocr, workers=workers, progress=progress)
    return pairs


def _score_crops(
    lines: Sequence[OcrPilotLine],
    crops: Mapping[str, bytes],
    ocr: Callable[[bytes], str],
    *,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, ...], ...]]:
    jobs = _crop_jobs(lines, crops)
    total = len(jobs)
    if total == 0:
        return (), ()
    if workers <= 1:
        pairs: list[tuple[str, str]] = []
        flags: list[tuple[str, ...]] = []
        for index, (reference, payload, line_flags) in enumerate(jobs, start=1):
            pairs.append((reference, ocr(payload)))
            flags.append(line_flags)
            if progress is not None:
                progress(index, total)
        return tuple(pairs), tuple(flags)
    ordered: list[tuple[str, str]] = [("", "")] * total
    ordered_flags: list[tuple[str, ...]] = [job[2] for job in jobs]
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {
            pool.submit(ocr, payload): index for index, (_ref, payload, _flags) in enumerate(jobs)
        }
        for future in as_completed(pending):
            index = pending[future]
            ordered[index] = (jobs[index][0], future.result())
            done += 1
            if progress is not None:
                progress(done, total)
    return tuple(ordered), tuple(ordered_flags)


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


def _bbox_pdf_pt(payload: Mapping[str, object]) -> tuple[float, float, float, float] | None:
    raw = payload.get("bbox_pdf_pt")
    if not isinstance(raw, list) or len(raw) != 4:
        return None
    numbers: list[float] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int | float):
            return None
        numbers.append(float(item))
    return (numbers[0], numbers[1], numbers[2], numbers[3])


def _short_side_pt(box: tuple[float, float, float, float]) -> float:
    return min(abs(box[2] - box[0]), abs(box[3] - box[1]))


def vertical_geometry(lines: Sequence[OcrPilotLine]) -> dict[str, object]:
    """Почему вертикальный срез не чинится поворотом кропа.

    Угол не подбирается по совпадению с эталоном. Короткая сторона рамки
    в пунктах PDF — свойство кропа до распознавания.
    """

    vertical = [line for line in lines if "VERTICAL" in line.flags]
    sides = [
        _short_side_pt(line.bbox_pdf_pt)
        for line in vertical
        if line.bbox_pdf_pt is not None
    ]
    sides.sort()
    median = sides[len(sides) // 2] if sides else None
    return {
        "n": len(vertical),
        "n_with_bbox": len(sides),
        "short_side_pt_median": median,
        "n_shorter_than_6pt": sum(1 for side in sides if side < 6.0),
        "rotation_search": False,
        "reason": (
            "Поворот на 90/270 и увеличение короткой стороны до 96 px "
            "на пробе 20 строк не подняли среднюю построчную CA выше 0,05. "
            "Рамки вертикальных строк часто короче 6 пт: глиф в кропе не читается. "
            "Угол по эталону не выбирается."
        ),
    }


def _pilot_flags(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Флаги строки пилота. Печать в jsonl не размечена и здесь не выдумывается."""

    found: list[str] = []
    if str(payload.get("orientation") or "").upper() == "ROTATED_OR_VERTICAL":
        found.append("VERTICAL")
    encoding = payload.get("encoding_flags")
    if isinstance(encoding, list) and encoding:
        found.append("LOW_QUALITY")
    return tuple(found)


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
                flags=_pilot_flags(payload),
                bbox_pdf_pt=_bbox_pdf_pt(payload),
            )
        )
    return tuple(rows)


def main() -> int:
    """CLI: замер на пилоте. Не печатает «гейт закрыт»."""

    from kontur.infrastructure.ocr_rapid import rapid_available, rapid_line_text
    from kontur.infrastructure.ocr_tesseract import (
        image_bytes_have_stamp,
        ocr_image_bytes,
        tesseract_available,
    )

    engine = os.environ.get(OCR_PILOT_ENGINE_ENV, "tesseract").strip().lower()
    scorer: Callable[[bytes], str]
    if engine == "tesseract":
        if not tesseract_available():
            print("tesseract/pytesseract нет; замер не выполнялся, гейт I открыт")
            return 3
        scorer = ocr_image_bytes
    elif engine == "eslav":
        if not rapid_available():
            print("eslav: нет весов по замку или rapidocr; замер не выполнялся, гейт I открыт")
            return 3
        scorer = rapid_line_text
    else:
        print(f"{OCR_PILOT_ENGINE_ENV}={engine}: ожидался tesseract или eslav")
        return 2
    path = find_pilot_zip()
    if path is None:
        print(f"нет корпуса: задайте {OCR_PILOT_ENV} или zip в files/02_*/ocr_pilot_20260811/")
        return 2
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
    pairs, line_flags = _score_crops(
        lines, readable, scorer, workers=workers, progress=_progress
    )
    tz = accuracy_interval(pairs)
    gate_i = gate_i_interval(pairs)
    accuracies = [character_accuracy(reference, hypothesis) for reference, hypothesis in pairs]
    mean_ca = sum(accuracies) / len(accuracies) if accuracies else 0.0
    pooled = judge_pooled_ocr(pairs, gold=False, line_flags=line_flags)
    report = {
        "pilot_path": str(path),
        "engine": engine,
        "n_pairs": len(pairs),
        "n_crops": len(crops),
        "n_stamp_excluded": n_stamp,
        "coverage": coverage,
        "workers": workers,
        "mean_ca": mean_ca,
        "character_accuracy": pooled,
        "tz_point": tz.point,
        "tz_low": tz.low,
        "tz_high": tz.high,
        "tz_n": tz.n,
        "tz_met": tz_character_accuracy_met(tz),
        "gate_i_point": gate_i.point,
        "gate_i_low": gate_i.low,
        "gate_i_n": gate_i.n,
        "vertical_geometry": vertical_geometry(lines),
        "silver_not_gold": True,
        "closes_gate_i": False,
        "note": (
            "character_accuracy — микро-CA по символам эталона. "
            "tz_* и gate_i_* — доля строк с построчным CA не ниже порога "
            "и её Уилсон; это другая величина. SILVER PDF_TEXT_LAYER, "
            "без Речникова. Гейт I открыт."
        ),
    }
    out_raw = os.environ.get(OCR_PILOT_OUT_ENV, "").strip()
    out_dir = Path(out_raw) if out_raw else Path.cwd() / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "ocr_pilot_ca.json" if engine == "tesseract" else f"ocr_pilot_ca_{engine}.json"
    out_path = out_dir / name
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {out_path}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
