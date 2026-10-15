"""CLI for TZ п. 11 timings: ``python -m kontur.cli.tz11 [--from-json file]``.

Results go to stdout (table, then one JSON line); diagnostics go to stderr via logging.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from kontur.evaluation.tz11 import evaluate, measure_local, render_table, timings_evidence

log = logging.getLogger("kontur.cli.tz11")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = list(sys.argv[1:] if argv is None else argv)
    measurements: dict[str, Any] = {}
    if "--from-json" in args:
        index = args.index("--from-json")
        if index + 1 >= len(args):
            log.error("usage: python -m kontur.evaluation.tz11 [--from-json file]")
            return 2
        loaded = json.loads(Path(args[index + 1]).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            log.error("ожидался объект измерений")
            return 2
        measurements.update(loaded)
    else:
        measurements.update(measure_local())
    results = evaluate(measurements)
    sys.stdout.write(render_table(results) + "\n")
    sys.stdout.write(json.dumps(timings_evidence(results), ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
