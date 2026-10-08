"""Сгенерировать публичные проверки из открытого JSONL.

    python -m kontur.evaluation.build_gold
    python -m kontur.evaluation.build_gold --check

`--check` падает, если `public_checks.jsonl` поправлен руками и больше не
совпадает с источником. Это не слепой замер: источник — открытый
TRAIN_PUBLIC, не скрытый тест. У каждой строки `blind` равен false.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from kontur.evaluation.dataset_package import (
    HIDDEN_TEST_OBJECT_IDS,
    LABELED_TRAIN_OBJECT_IDS,
)
from kontur.evaluation.inventory import require_path_open

SOURCE_NAME = "public_gold_checks.jsonl"
SOURCE_REL = Path("data/dataset/gold/sources") / SOURCE_NAME
OUTPUT_REL = Path("data/dataset/gold/public_checks.jsonl")
EXPECTED_IDS = tuple(f"TRAIN-{index:04d}" for index in range(1, 16))
_PROJECTION = (
    "check_id",
    "object_id",
    "parameter_code",
    "violation_label",
    "score_eligible",
    "gold_status",
    "matrix_scope",
    "location",
)


class GoldBuildError(ValueError):
    """Источник нельзя переписать в эталон, не выдумывая метку."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def build_records(source: Path) -> list[dict[str, object]]:
    """Строки источника плюс SHA и пометка, что замер не слепой."""

    target = require_path_open(source)
    raw = target.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    records: list[dict[str, object]] = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GoldBuildError(f"{target.name}:{number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise GoldBuildError(f"{target.name}:{number}: ожидался объект")
        object_id = str(payload.get("object_id") or "")
        allowed = object_id in LABELED_TRAIN_OBJECT_IDS
        if object_id in HIDDEN_TEST_OBJECT_IDS or not allowed:
            raise GoldBuildError(
                f"{target.name}:{number}: объект {object_id} не из открытого train"
            )
        label = payload.get("violation_label")
        if label not in {"VIOLATION_PRESENT", "NO_VIOLATION"}:
            raise GoldBuildError(f"{target.name}:{number}: неизвестная метка {label!r}")
        stamped = dict(payload)
        stamped["_source"] = SOURCE_NAME
        stamped["_source_sha256"] = digest
        stamped["blind"] = False
        if label == "NO_VIOLATION":
            stamped["fpr_denominator"] = True
        records.append(stamped)
    ids = [str(item["check_id"]) for item in records]
    if tuple(ids) != EXPECTED_IDS:
        raise GoldBuildError(f"{target.name}: ожидались {EXPECTED_IDS}, получено {ids}")
    return records


def render(records: Sequence[Mapping[str, object]]) -> str:
    return "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
    )


def scoring_row(record: Mapping[str, object]) -> dict[str, object]:
    """Поля, которые карточка инвентаря не имеет права разойти с генератором."""

    projected = {key: record[key] for key in _PROJECTION}
    if record.get("fpr_denominator") is True:
        projected["fpr_denominator"] = True
    return projected


def generated_text(root: Path | None = None) -> str:
    base = root or repo_root()
    return render(build_records(base / SOURCE_REL))


def check(root: Path | None = None) -> list[str]:
    """Имена файлов, которые не совпали с генератором. Пустой список — актуально."""

    base = root or repo_root()
    expected = generated_text(base)
    target = base / OUTPUT_REL
    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    if current != expected:
        return [OUTPUT_REL.as_posix()]
    return []


def write(root: Path | None = None) -> Path:
    base = root or repo_root()
    target = base / OUTPUT_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generated_text(base), encoding="utf-8", newline="\n")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Публичные проверки из открытого JSONL")
    parser.add_argument(
        "--check",
        action="store_true",
        help="выйти с 1, если сгенерированный файл разошёлся с источником",
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        if args.check:
            stale = check(args.root)
        else:
            path = write(args.root)
            print(f"{path.relative_to(args.root or repo_root()).as_posix()}: записан")
            stale = []
    except (GoldBuildError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if stale:
        print("эталон устарел, перегенерируйте: " + ", ".join(stale), file=sys.stderr)
        return 1
    if args.check:
        print("эталон актуален")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
