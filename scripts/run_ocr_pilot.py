"""CLI-обёртка: python scripts/run_ocr_pilot.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.evaluation.ocr_pilot import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
