"""Shared test fixtures; insecure legacy authentication is opt-in per module."""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture
def legacy_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Enable the temporary legacy grammar for the compatibility API module only."""

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    yield


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Attach compatibility explicitly to the one pre-JWT regression module."""

    for item in items:
        if item.path.name == "test_api.py":
            item.add_marker(pytest.mark.usefixtures("legacy_auth_enabled"))
