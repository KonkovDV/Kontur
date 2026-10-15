"""Hardening: insecure auth и clamd вне dev."""

import pytest

from kontur.infrastructure.clamd import AvStatus, clamd_required, scan_from_env
from kontur.presentation.auth import insecure_auth_permitted


@pytest.mark.parametrize("env", ["dev", "demo", "test", "local"])
def test_insecure_auth_allowed_in_dev_envs(monkeypatch, env):
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.setenv("KONTUR_ENV", env)
    assert insecure_auth_permitted()


@pytest.mark.parametrize("env", ["production", "staging", "prod"])
def test_insecure_auth_blocked_outside_demo(monkeypatch, env):
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.setenv("KONTUR_ENV", env)
    assert not insecure_auth_permitted()


def test_clamd_required_in_production(monkeypatch):
    monkeypatch.setenv("KONTUR_ENV", "production")
    monkeypatch.delenv("KONTUR_CLAMD_REQUIRED", raising=False)
    monkeypatch.delenv("KONTUR_CLAMD_HOST", raising=False)
    assert clamd_required()
    status, _ = scan_from_env(b"x")
    assert status is AvStatus.UNAVAILABLE


def test_clamd_optional_in_dev(monkeypatch):
    monkeypatch.setenv("KONTUR_ENV", "dev")
    monkeypatch.delenv("KONTUR_CLAMD_REQUIRED", raising=False)
    monkeypatch.delenv("KONTUR_CLAMD_HOST", raising=False)
    assert not clamd_required()
    status, _ = scan_from_env(b"x")
    assert status is AvStatus.NOT_CONFIGURED
