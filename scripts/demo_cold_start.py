"""Чеклист холодного демо (#78). Не видео, не Polar, не TEST_HIDDEN."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from kontur.evaluation.demo_cold_start import (  # noqa: E402
    CLOSES_GATE_J,
    CLOSES_GATE_K,
    COMPOSE_DEMO_SERVICES,
    DEFAULT_HEALTHZ_URL,
    DEMO_CODES,
    DEMO_OBJECT_ID,
    assert_honest_coverage,
    preflight,
)
from kontur.infrastructure.matrix.registry import FileRuleRegistry  # noqa: E402
from kontur.infrastructure.synthetic_pdf import contest_slice_font  # noqa: E402


def _probe(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - адрес задаёт оператор
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return f"{url} ответил {exc.code}"
    except (OSError, ValueError) as exc:
        return f"{url} недоступен ({exc.__class__.__name__})"
    if body != {"status": "ok"}:
        return f"{url} ответил {body!r} вместо {{\"status\": \"ok\"}}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="проверить флаг legacy-токенов, шрифт и /healthz ядра; код 1 при проблеме",
    )
    parser.add_argument("--healthz", default=DEFAULT_HEALTHZ_URL, help="адрес /healthz ядра")
    parser.add_argument(
        "--skip-healthz", action="store_true", help="не ходить в ядро (офлайн-проверка)"
    )
    args = parser.parse_args(argv)
    if args.preflight:
        url = str(args.healthz)
        problems = preflight(
            os.environ,
            font=contest_slice_font(),
            healthz=None if args.skip_healthz else (lambda: _probe(url)),
        )
        for problem in problems:
            print(f"PREFLIGHT FAIL {problem}", file=sys.stderr)
        if problems:
            return 1
        print("preflight ok")
    report = FileRuleRegistry().coverage_report()
    assert_honest_coverage(report)
    print(
        "coverage advisory={advisory} executable={executable} "
        "extractor_missing={extractor_missing} not_applicable={not_applicable} "
        "source_missing={source_missing} declared={declared}".format(**report)
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
