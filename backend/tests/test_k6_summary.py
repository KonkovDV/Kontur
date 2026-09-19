"""Gate L report must preserve exact k6 measurements and fail closed."""

from __future__ import annotations

import pytest

from scripts.render_k6_summary import build_report, render_markdown


def _summary(*, p95: float = 12.5, error_rate: float = 0.0) -> dict[str, object]:
    return {
        "metrics": {
            "http_req_duration{name:status}": {
                "values": {"med": 8.0, "p(95)": p95, "p(99)": 20.0}
            },
            "http_req_failed{name:status}": {"values": {"rate": error_rate}},
            "kontur_status_requests": {"values": {"count": 6000}},
        }
    }


def test_report_records_shape_and_passes_thresholds() -> None:
    report = build_report(_summary(), git_sha="a" * 40, stand="gha-ubuntu")
    assert report["status"] == "PASS"
    assert report["vus"] == 100
    assert report["duration_seconds"] == 60
    assert report["requests"] == 6000
    assert report["p50_ms"] == 8.0
    assert report["p95_ms"] == 12.5
    assert report["p99_ms"] == 20.0
    markdown = render_markdown(report)
    assert "p50/p95/p99: 8.00 / 12.50 / 20.00 ms" in markdown


@pytest.mark.parametrize(
    ("p95", "error_rate"),
    [(200.0, 0.0), (12.5, 0.01), (250.0, 0.02)],
)
def test_report_fails_closed_on_threshold_boundary(
    p95: float,
    error_rate: float,
) -> None:
    report = build_report(
        _summary(p95=p95, error_rate=error_rate),
        git_sha="b" * 40,
        stand="test",
    )
    assert report["status"] == "FAIL"


def test_missing_tagged_metric_is_not_replaced_with_global_metric() -> None:
    summary = _summary()
    metrics = summary["metrics"]
    assert isinstance(metrics, dict)
    metrics.pop("http_req_duration{name:status}")
    metrics["http_req_duration"] = {
        "values": {"med": 1.0, "p(95)": 1.0, "p(99)": 1.0}
    }
    with pytest.raises(ValueError, match="name:status"):
        build_report(summary, git_sha="c" * 40, stand="test")
