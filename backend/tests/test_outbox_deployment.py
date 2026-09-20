"""Static deployment contract for the dedicated relay container."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_relay_has_a_separate_least_privilege_container() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "backend" / "Dockerfile.relay").read_text(encoding="utf-8")
    assert "outbox-relay:" in compose
    assert "dockerfile: backend/Dockerfile.relay" in compose
    assert 'user: "10001:10001"' in compose
    assert "read_only: true" in compose
    assert "cap_drop: [ALL]" in compose
    assert "no-new-privileges:true" in compose
    assert "restart: unless-stopped" in compose
    assert 'USER 10001:10001' in dockerfile
    assert '".[queue,store]"' in dockerfile
    assert "relay_outbox.py" in dockerfile


def test_relay_is_present_in_offline_override() -> None:
    offline = (ROOT / "docker-compose.offline.yml").read_text(encoding="utf-8")
    assert "outbox-relay:" in offline
    assert "pull_policy: never" in offline


def test_broker_contract_is_confirmed_persistent_and_bounded() -> None:
    source = (
        ROOT / "backend" / "src" / "kontur" / "infrastructure" / "broker.py"
    ).read_text(encoding="utf-8")
    assert "publisher_confirms=True" in source
    assert "on_return_raises=True" in source
    assert '"x-queue-type": "quorum"' in source
    assert "DeliveryMode.PERSISTENT" in source
    assert "mandatory=True" in source
    assert "timeout=self._timeout_seconds" in source
