"""Shared test fixtures; insecure legacy authentication is opt-in per module."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def legacy_auth_enabled(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Enable the temporary legacy grammar for the compatibility API module only."""

    if request.node.path.name == "test_api.py":
        monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    yield
