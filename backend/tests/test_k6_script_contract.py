"""Static contract for the k6 status harness; CI does not execute k6."""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tests" / "load" / "k6_status.js"


def _src() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_k6_script_declares_tz_load_shape_and_requires_jwt_env() -> None:
    src = _src()
    assert SCRIPT.is_file()
    assert re.search(r"vus\s*:\s*100", src)
    assert re.search(r"duration\s*:\s*['\"]60s['\"]", src)
    assert "p(95)<200" in src
    assert "http_req_duration{name:status}" in src
    assert "http_req_failed" in src
    assert "rate<0.01" in src
    assert "/status" in src
    assert "FormData" not in src
    assert "tags: { name: 'status' }" in src
    assert "KONTUR_BEARER_TOKEN" in src
    assert "KONTUR_TOKEN" not in src
    assert "insp-7@obj-load/INSPECTOR" not in src
