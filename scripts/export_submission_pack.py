"""Собрать пакет сдачи в out/. Не закрывает гейты, не Polar, не TEST_HIDDEN."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.evaluation.submission_pack import build_submission_pack  # noqa: E402


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    pack = build_submission_pack(root=root)
    target = root / "out" / "submission_pack.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    coverage = pack["coverage"]
    print(target)
    print(
        "coverage executable={executable} extractor_missing={extractor_missing} "
        "declared={declared}".format(**coverage)
    )
    print(
        "closes_gate_i={closes_gate_i} closes_gate_j={closes_gate_j} "
        "closes_gate_k={closes_gate_k}".format(**pack)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
