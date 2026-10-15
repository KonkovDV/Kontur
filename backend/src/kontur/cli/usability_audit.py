"""CLI for the usability audit: ``python -m kontur.cli.usability_audit <dir-or-file>``.

The JSON report goes to stdout; diagnostics go to stderr via logging.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from kontur.evaluation.usability_audit import load_audit

log = logging.getLogger("kontur.cli.usability_audit")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        log.error("usage: python -m kontur.evaluation.usability_audit <dir-or-file>")
        return 2
    report = load_audit(Path(args[0]))
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
