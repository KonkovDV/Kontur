"""§13 п.1: JSON-лог с шестью полями ТЗ + сквозной request_id."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from kontur.presentation import json_logging as jl
from kontur.presentation.json_logging import (
    TZ_LOG_FIELDS,
    TzJsonFormatter,
    configure_json_logging,
    request_id_var,
    resolve_user_id,
    user_id_var,
)


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    jl.reset_json_logging_for_tests()
    yield
    jl.reset_json_logging_for_tests()


def test_json_log_has_six_tz_fields() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TzJsonFormatter(service="kontur-core"))
    logger = logging.getLogger("test.tz_json_fields")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    tok_r = request_id_var.set("rid-test-1")
    tok_u = user_id_var.set("inspector-42")
    try:
        logger.info("pipeline started")
    finally:
        request_id_var.reset(tok_r)
        user_id_var.reset(tok_u)

    line = stream.getvalue().strip()
    data = json.loads(line)
    assert set(TZ_LOG_FIELDS) <= set(data.keys())
    assert data["level"] == "INFO"
    assert data["service"] == "kontur-core"
    assert data["message"] == "pipeline started"
    assert data["request_id"] == "rid-test-1"
    assert data["user_id"] == "inspector-42"
    # timestamp парсится как ISO-8601 UTC
    parsed = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_user_id_anonymous_without_auth() -> None:
    assert resolve_user_id(None) == "anonymous"
    assert resolve_user_id("") == "anonymous"
    assert resolve_user_id("Bearer ") == "anonymous"


def test_request_id_propagated_from_header() -> None:
    configure_json_logging(service="kontur-core")
    from kontur.presentation.api import app

    client = TestClient(app)
    response = client.get("/api/v1/healthz", headers={"x-request-id": "client-rid-99"})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "client-rid-99"


def test_request_id_generated_when_missing() -> None:
    configure_json_logging(service="kontur-core")
    from kontur.presentation.api import app

    client = TestClient(app)
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    rid = response.headers.get("x-request-id")
    assert rid is not None and len(rid) >= 8
