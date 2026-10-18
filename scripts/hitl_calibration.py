"""SILVER-отчёт калибровки HITL: JSONL {confidence, correct, split} → JSON + SVG.

Без входа пишет честный отчёт ``uncalibrated`` (n=0). Hidden split отвергается.
Использование: python scripts/hitl_calibration.py [samples.jsonl] [--out out/]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.evaluation.calibration import (  # noqa: E402
    calibration_report,
    load_samples,
    reliability_svg,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", nargs="?")
    ap.add_argument("--out", default="out")
    ap.add_argument("--max-error-rate", type=float, default=0.10)
    ap.add_argument("--min-n", type=int, default=30)
    args = ap.parse_args()
    rows = []
    if args.samples:
        rows = [
            json.loads(line)
            for line in Path(args.samples).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    sha = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
    ).stdout.strip()
    report = calibration_report(
        load_samples(rows),
        max_error_rate=args.max_error_rate,
        min_n=args.min_n,
        git_sha=sha,
        date=dt.date.today().isoformat(),
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hitl_calibration_silver.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "hitl_reliability_silver.svg").write_text(reliability_svg(report), encoding="utf-8")
    print(
        json.dumps(
            {k: report[k] for k in ("n", "ece", "t_high", "status", "closes_gate")},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
