#!/usr/bin/env python3
"""Тонкая обёртка: см. ``kontur.cli.check_storage_integrity`` (§13 п.8)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.cli.check_storage_integrity import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
