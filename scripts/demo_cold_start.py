"""Чеклист холодного демо (#78). Не видео, не Polar, не TEST_HIDDEN."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.evaluation.demo_cold_start import (  # noqa: E402
    CLOSES_GATE_J,
    CLOSES_GATE_K,
    COMPOSE_DEMO_SERVICES,
    DEMO_CODES,
    DEMO_OBJECT_ID,
    assert_honest_coverage,
)
from kontur.infrastructure.matrix.registry import FileRuleRegistry  # noqa: E402


def main() -> int:
    report = FileRuleRegistry().coverage_report()
    assert_honest_coverage(report)
    print(
        "coverage executable={executable} extractor_missing={extractor_missing} "
        "declared={declared}".format(**report)
    )
    print(f"object_id={DEMO_OBJECT_ID}")
    print(f"codes={','.join(DEMO_CODES)}")
    print(f"compose={' '.join(COMPOSE_DEMO_SERVICES)}")
    print(f"closes_gate_j={str(CLOSES_GATE_J).lower()} closes_gate_k={str(CLOSES_GATE_K).lower()}")
    print()
    print("Репетиция (CI, без Polar):")
    print("  python -m pytest backend/tests/test_demo_cold_start.py -q --tb=short")
    print("Compose на чистой машине: docs/DEMO_COLD_START.md")
    print("Видео запасного демо пишет человек, не этот скрипт.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
