"""Предполётная проверка демо и запрет флага legacy-токенов в pilot/prod."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from kontur.evaluation.demo_cold_start import preflight
from kontur.presentation.auth import assert_insecure_auth_allowed

ROOT = Path(__file__).resolve().parents[2]
DEMO_ENV = {"KONTUR_ALLOW_INSECURE_DEV_AUTH": "true", "KONTUR_ENV": "demo"}


def _ok() -> None:
    return None


def test_preflight_passes_for_demo(tmp_path: Path) -> None:
    font = tmp_path / "f.ttf"
    font.write_bytes(b"x")
    assert preflight(DEMO_ENV, font=font, healthz=_ok) == []


@pytest.mark.parametrize("env", ["pilot", "prod", "Prod", " production "])
def test_preflight_blocks_insecure_flag_outside_demo(env: str, tmp_path: Path) -> None:
    font = tmp_path / "f.ttf"
    font.write_bytes(b"x")
    problems = preflight(
        {"KONTUR_ALLOW_INSECURE_DEV_AUTH": "true", "KONTUR_ENV": env}, font=font, healthz=None
    )
    assert len(problems) == 1
    assert problems[0].startswith("флаг:") and "ядро не стартует" in problems[0]


def test_preflight_names_every_problem() -> None:
    problems = preflight({}, font=None, healthz=lambda: "http://x/healthz недоступен")
    assert [p.split(":", 1)[0] for p in problems] == ["флаг", "шрифт", "ядро"]
    assert "KONTUR_ENV=demo" in problems[0]
    assert "KONTUR_TEST_FONT" in problems[1]
    assert "недоступен" in problems[2]


@pytest.mark.parametrize("env", ["pilot", "prod", "staging", "test", "local"])
def test_core_refuses_to_start_with_insecure_flag(
    env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.setenv("KONTUR_ENV", env)
    with pytest.raises(RuntimeError, match=f"KONTUR_ENV={env}"):
        assert_insecure_auth_allowed()


@pytest.mark.parametrize("env", ["demo", "dev", "Demo", " dev "])
def test_core_starts_with_insecure_flag_in_dev_envs(
    env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.setenv("KONTUR_ENV", env)
    assert_insecure_auth_allowed()


def test_script_preflight_exits_1_with_readable_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = importlib.util.spec_from_file_location(
        "demo_cold_start_script", ROOT / "scripts" / "demo_cold_start.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.setenv("KONTUR_ENV", "prod")
    code = module.main(["--preflight", "--healthz", "http://127.0.0.1:9/api/v1/healthz"])
    err = capsys.readouterr().err
    assert code == 1
    assert "PREFLIGHT FAIL флаг:" in err
    assert "PREFLIGHT FAIL ядро: http://127.0.0.1:9/api/v1/healthz недоступен" in err


@pytest.mark.parametrize("value", [None, "", "   "])
def test_core_refuses_flag_without_explicit_env(
    value: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    if value is None:
        monkeypatch.delenv("KONTUR_ENV", raising=False)
    else:
        monkeypatch.setenv("KONTUR_ENV", value)
    with pytest.raises(RuntimeError, match="KONTUR_ENV не задан"):
        assert_insecure_auth_allowed()


def test_empty_env_without_flag_still_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", raising=False)
    monkeypatch.delenv("KONTUR_ENV", raising=False)
    assert_insecure_auth_allowed()


def test_legacy_tokens_and_demo_kit_need_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from kontur.presentation.api import app
    from kontur.presentation.auth import insecure_auth_permitted

    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    monkeypatch.delenv("KONTUR_ENV", raising=False)
    assert insecure_auth_permitted() is False
    response = TestClient(app).post(
        "/api/v1/demo/kit", headers={"Authorization": "Bearer inspector@OBJ-1/inspector"}
    )
    assert response.status_code == 404


def test_preflight_rejects_flag_without_env(tmp_path: Path) -> None:
    font = tmp_path / "f.ttf"
    font.write_bytes(b"x")
    (problem,) = preflight({"KONTUR_ALLOW_INSECURE_DEV_AUTH": "true"}, font=font, healthz=None)
    assert "без KONTUR_ENV" in problem and "KONTUR_ENV=demo" in problem


def test_demo_compose_and_runbook_set_env_demo() -> None:
    compose = (ROOT / "docker-compose.demo.yml").read_text(encoding="utf-8")
    assert "KONTUR_ENV: demo" in compose
    runbook = (ROOT / "docs" / "DEMO_COLD_START.md").read_text(encoding="utf-8")
    assert "`KONTUR_ENV=demo`" in runbook
