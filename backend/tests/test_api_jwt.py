"""Signed-JWT regressions at the HTTP authentication and object-scope boundary."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
ISSUER = "https://issuer.test/"
AUDIENCE = "kontur-api"


@pytest.fixture
def rsa_private() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    rsa_private: rsa.RSAPrivateKey,
) -> Iterator[TestClient]:
    previous_workspace = app.state.workspace
    public = rsa_private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.delenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", raising=False)
    monkeypatch.setenv("KONTUR_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("KONTUR_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("KONTUR_JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("KONTUR_JWT_PUBLIC_KEY", public)
    app.state.workspace = ProcessWorkspace()
    try:
        yield TestClient(app)
    finally:
        app.state.workspace = previous_workspace


def _claims(**changes: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "insp-7",
        "roles": ["INSPECTOR"],
        "object_id": "OBJ-001",
        "nbf": (now - timedelta(seconds=1)).timestamp(),
        "exp": (now + timedelta(minutes=5)).timestamp(),
    }
    claims.update(changes)
    return claims


def _headers(
    private: object,
    algorithm: str = "RS256",
    **changes: object,
) -> dict[str, str]:
    token = jwt.encode(_claims(**changes), private, algorithm=algorithm)
    return {"Authorization": f"Bearer {token}"}


def _status(client: TestClient, headers: dict[str, str]) -> object:
    return client.get("/api/v1/processes/not-created/status", headers=headers)


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": (datetime.now(UTC) - timedelta(seconds=1)).timestamp()},
        {"nbf": (datetime.now(UTC) + timedelta(minutes=5)).timestamp()},
        {"iss": "https://attacker.invalid/"},
        {"aud": "other-api"},
        {"aud": [AUDIENCE]},
    ],
)
def test_invalid_jwt_is_401_without_side_effects(
    changes: dict[str, object],
    client: TestClient,
    rsa_private: rsa.RSAPrivateKey,
) -> None:
    response = _status(client, _headers(rsa_private, **changes))
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication required"}
    assert app.state.workspace._items == {}


def test_forged_jwt_is_401_without_side_effects(
    client: TestClient,
    rsa_private: rsa.RSAPrivateKey,
) -> None:
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = _status(client, _headers(attacker))
    assert response.status_code == 401
    assert app.state.workspace._items == {}


def test_malformed_dotted_token_is_401_even_with_dev_flag(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    response = _status(
        client,
        {"Authorization": "Bearer insp-7@OBJ-001/INSPECTOR.suffix"},
    )
    assert response.status_code == 401
    assert app.state.workspace._items == {}


def test_legacy_token_is_401_by_default(client: TestClient) -> None:
    response = _status(
        client,
        {"Authorization": "Bearer insp-7@OBJ-001/INSPECTOR"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("roles", [["UNKNOWN"], ["ADMIN"]])
def test_unknown_or_insufficient_role_is_403(
    roles: list[str],
    client: TestClient,
    rsa_private: rsa.RSAPrivateKey,
) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        headers=_headers(rsa_private, roles=roles),
        data={"object_id": "OBJ-001", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert response.status_code == 403
    assert app.state.workspace._items == {}


def test_missing_object_scope_on_object_endpoint_is_403(
    client: TestClient,
    rsa_private: rsa.RSAPrivateKey,
) -> None:
    claims = _claims()
    del claims["object_id"]
    token = jwt.encode(claims, rsa_private, algorithm="RS256")
    response = client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"object_id": "OBJ-001", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert response.status_code == 403
    assert app.state.workspace._items == {}


def test_valid_es256_happy_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("KONTUR_JWT_ALGORITHM", "ES256")
    monkeypatch.setenv("KONTUR_JWT_PUBLIC_KEY", public)
    response = client.post(
        "/api/v1/documents/upload",
        headers=_headers(private, "ES256"),
        data={"object_id": "OBJ-001", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert response.status_code == 202


def test_valid_wrong_object_is_403_without_side_effects(
    client: TestClient,
    rsa_private: rsa.RSAPrivateKey,
) -> None:
    created = client.post(
        "/api/v1/documents/upload",
        headers=_headers(rsa_private),
        data={"object_id": "OBJ-001", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    snapshot = record.to_status()
    files_before = tuple(record.files)
    audit_before = tuple(record.audit.records)

    denied = client.get(
        f"/api/v1/processes/{process_id}/status",
        headers=_headers(rsa_private, object_id="OBJ-OTHER"),
    )
    assert denied.status_code == 403
    assert denied.json() == {"detail": "access denied"}
    assert "OBJ-001" not in denied.text
    assert "OBJ-OTHER" not in denied.text
    assert record.to_status() == snapshot
    assert tuple(record.files) == files_before
    assert tuple(record.audit.records) == audit_before
