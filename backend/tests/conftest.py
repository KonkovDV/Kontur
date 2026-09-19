"""Test-only compatibility for pre-JWT API access-control regression fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _explicit_legacy_auth_for_existing_api_fixtures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Existing access-control tests intentionally exercise the legacy token shape.
    # Production defaults remain fail-closed; strict JWT tests delete this variable.
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
