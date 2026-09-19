"""Выгрузка снимков для следующего ИИ: coverage, handoff, индекс TRAIN_PUBLIC."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.evaluation.agent_dumps import export_all  # noqa: E402


def main() -> int:
    written = export_all()
    report = {key: str(path) for key, path in written.items()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
