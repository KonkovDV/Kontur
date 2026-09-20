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
    assert "USER 10001:10001" in dockerfile
    assert '".[queue,store]"' in dockerfile
    assert "relay_outbox.py" in dockerfile
    assert "consume_inbox.py" in dockerfile
    assert "inbox-consumer:" in compose
    assert "/app/consume_inbox.py" in compose


def test_relay_is_present_in_offline_override() -> None:
    offline = (ROOT / "docker-compose.offline.yml").read_text(encoding="utf-8")
    assert "outbox-relay:" in offline
    assert "inbox-consumer:" in offline
    assert "pull_policy: never" in offline


def test_rabbitmq_is_reachable_and_durable_inside_compose() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "RABBITMQ_DEFAULT_USER: kontur" in compose
    assert "RABBITMQ_DEFAULT_PASS: kontur" in compose
    assert "amqp://kontur:kontur@rabbitmq:5672/" in compose
    assert "amqp://guest:guest@rabbitmq:5672/" not in compose
    assert "rabbitmq:/var/lib/rabbitmq" in compose
    assert "rabbitmq:" in compose.split("volumes:", maxsplit=1)[1]


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
    assert "PREFETCH_COUNT = 1" in source
    assert "DEAD_LETTER_EXCHANGE" in source
    assert "x-delivery-limit" in source
    assert "protocol_queue_arguments" in source


def test_classic_amqp_publisher_and_guest_compose_identity_are_gone() -> None:
    outbox = (
        ROOT / "backend" / "src" / "kontur" / "infrastructure" / "outbox.py"
    ).read_text(encoding="utf-8")
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    dockerfile = (ROOT / "backend" / "Dockerfile.relay").read_text(encoding="utf-8")
    assert "class AmqpConfirmedPublisher" not in outbox
    assert "declare_queue" not in outbox
    assert "amqp://guest:guest@" not in env
    assert "amqp://kontur:kontur@localhost:5672/" in env
    assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
