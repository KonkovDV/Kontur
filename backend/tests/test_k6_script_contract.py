"""Static contract for the live Gate L k6 harness and JWT-only authentication."""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tests" / "load" / "k6_status.js"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_k6_script_preserves_live_gate_l_invariants() -> None:
    src = _src()
    assert SCRIPT.is_file()
    assert re.search(r"vus\s*:\s*100", src)
    assert re.search(r"duration\s*:\s*['\"]60s['\"]", src)
    assert "p(95)<200" in src
    assert "http_req_duration{name:status}" in src
    assert "http_req_failed{name:status}" in src
    assert "rate<0.01" in src
    assert "summaryTrendStats" in src
    assert "'p(99)'" in src
    assert "kontur_status_requests" in src
    assert "statusRequests.add(1)" in src
    assert "sleep(1)" in src
    assert "name: 'setup-upload'" in src
    assert "tags: { name: 'status' }" in src
    assert "http.post" in src
    assert "/api/v1/documents/upload" in src
    assert "/status" in src
    assert "handleSummary" in src
    assert "/work/out/k6-summary.json" in src
    assert "FormData" not in src


def test_k6_script_requires_only_jwt_bearer_environment() -> None:
    src = _src()
    assert "const TOKEN = __ENV.KONTUR_BEARER_TOKEN;" in src
    assert "KONTUR_BEARER_TOKEN is required" in src
    assert "KONTUR_TOKEN" not in src
    assert "insp-7@obj-load/INSPECTOR" not in src
    assert not re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.", src)
