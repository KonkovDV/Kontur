"""Render a machine-readable and Markdown Gate L report from k6 summary JSON."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

DURATION_METRIC = "http_req_duration{name:status}"
FAILED_METRIC = "http_req_failed{name:status}"
REQUESTS_METRIC = "kontur_status_requests"


def _values(metrics: dict[str, Any], name: str) -> dict[str, float]:
    metric = metrics.get(name)
    if not isinstance(metric, dict) or not isinstance(metric.get("values"), dict):
        raise ValueError(f"k6 summary не содержит metric {name!r}")
    values = metric["values"]
    return {str(key): float(value) for key, value in values.items()}


def build_report(summary: dict[str, Any], *, git_sha: str, stand: str) -> dict[str, Any]:
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("k6 summary не содержит metrics")
    duration = _values(metrics, DURATION_METRIC)
    failed = _values(metrics, FAILED_METRIC)
    requests = _values(metrics, REQUESTS_METRIC)
    required = {"med", "p(95)", "p(99)"}
    missing = required - duration.keys()
    if missing:
        raise ValueError(f"k6 summary не содержит trend stats: {sorted(missing)}")
    if "rate" not in failed or "count" not in requests:
        raise ValueError("k6 summary не содержит error rate или request count")

    p95 = duration["p(95)"]
    error_rate = failed["rate"]
    passed = p95 < 200.0 and error_rate < 0.01 and requests["count"] > 0
    return {
        "gate": "L",
        "status": "PASS" if passed else "FAIL",
        "git_sha": git_sha,
        "stand": stand,
        "vus": 100,
        "duration_seconds": 60,
        "requests": int(requests["count"]),
        "p50_ms": duration["med"],
        "p95_ms": p95,
        "p99_ms": duration["p(99)"],
        "error_rate": error_rate,
        "thresholds": {"p95_ms_lt": 200, "error_rate_lt": 0.01},
    }


def render_markdown(report: dict[str, Any]) -> str:
    return (
        "## Gate L — live k6\n\n"
        f"- Status: **{report['status']}**\n"
        f"- Git SHA: `{report['git_sha']}`\n"
        f"- Stand: {report['stand']}\n"
        f"- Load: {report['vus']} VU × {report['duration_seconds']} s\n"
        f"- Requests: {report['requests']}\n"
        f"- p50/p95/p99: {report['p50_ms']:.2f} / "
        f"{report['p95_ms']:.2f} / {report['p99_ms']:.2f} ms\n"
        f"- Error rate: {report['error_rate']:.6f}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()

    raw = json.loads(args.summary.read_text(encoding="utf-8"))
    report = build_report(
        raw,
        git_sha=os.environ.get("GITHUB_SHA", "unspecified"),
        stand=os.environ.get("KONTUR_LOAD_STAND", "unspecified"),
    )
    args.json_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_out.write_text(render_markdown(report), encoding="utf-8")
    if report["status"] != "PASS":
        raise SystemExit("Gate L thresholds failed")


if __name__ == "__main__":
    main()
