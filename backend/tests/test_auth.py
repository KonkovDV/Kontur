"""Verified JWT authentication and explicit local-development compatibility."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from kontur.presentation.auth import parse_bearer
from kontur.presentation.rbac import AuthenticationRequiredError

ISSUER = "https://issuer.test/"
AUDIENCE = "kontur-api"


@pytest.fixture(scope="module")
def rsa_keys() -> tuple[object, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


def _configure(monkeypatch: pytest.MonkeyPatch, public: str, algorithm: str = "RS256") -> None:
    monkeypatch.delenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", raising=False)
    monkeypatch.setenv("KONTUR_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("KONTUR_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("KONTUR_JWT_ALGORITHM", algorithm)
    monkeypatch.setenv("KONTUR_JWT_PUBLIC_KEY", public)


def _claims(**changes: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "insp-7",
        "roles": ["INSPECTOR"],
        "object_id": "OBJ-001",
        "nbf": now - timedelta(seconds=1),
        "exp": now + timedelta(minutes=5),
    }
    claims.update(changes)
    return claims


def _token(private: object, **changes: object) -> str:
    return jwt.encode(_claims(**changes), private, algorithm="RS256")


def _reject(token: str | None) -> None:
    with pytest.raises(AuthenticationRequiredError, match="^authentication required$"):
        parse_bearer(None if token is None else f"Bearer {token}")


def test_valid_signed_rsa_jwt(rsa_keys: tuple[object, str], monkeypatch: pytest.MonkeyPatch) -> None:
    private, public = rsa_keys
    _configure(monkeypatch, public)
    context = parse_bearer(f"Bearer {_token(private)}")
    assert context.subject == "insp-7"
    assert context.roles == ("INSPECTOR",)
    assert context.object_id == "OBJ-001"


def test_forged_signature(rsa_keys: tuple[object, str], monkeypatch: pytest.MonkeyPatch) -> None:
    _, public = rsa_keys
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _configure(monkeypatch, public)
    _reject(_token(attacker))


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"nbf": datetime.now(UTC) + timedelta(minutes=5)},
        {"iss": "https://attacker.invalid/"},
        {"aud": "other-api"},
        {"sub": ""},
        {"roles": []},
        {"roles": "INSPECTOR"},
        {"roles": [""]},
        {"object_id": ""},
    ],
)
def test_invalid_claims_are_uniformly_rejected(
    changes: dict[str, object],
    rsa_keys: tuple[object, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, public = rsa_keys
    _configure(monkeypatch, public)
    _reject(_token(private, **changes))


def test_missing_required_claim(rsa_keys: tuple[object, str], monkeypatch: pytest.MonkeyPatch) -> None:
    private, public = rsa_keys
    _configure(monkeypatch, public)
    claims = _claims()
    del claims["roles"]
    _reject(jwt.encode(claims, private, algorithm="RS256"))


def test_mismatched_algorithm(rsa_keys: tuple[object, str], monkeypatch: pytest.MonkeyPatch) -> None:
    _, public = rsa_keys
    ec_private = ec.generate_private_key(ec.SECP256R1())
    _configure(monkeypatch, public, "RS256")
    _reject(jwt.encode(_claims(), ec_private, algorithm="ES256"))


def test_none_algorithm_is_rejected(rsa_keys: tuple[object, str], monkeypatch: pytest.MonkeyPatch) -> None:
    _, public = rsa_keys
    _configure(monkeypatch, public)
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()  # noqa: E731
    token = f"{encode(json.dumps({'alg': 'none'}).encode())}.{encode(json.dumps(_claims(), default=str).encode())}."
    _reject(token)


def test_legacy_rejected_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", raising=False)
    _reject("insp-7@OBJ-001/INSPECTOR")


def test_explicit_dev_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    context = parse_bearer("Bearer insp-7@OBJ-001/INSPECTOR")
    assert context.subject == "insp-7"
    assert context.roles == ("INSPECTOR",)
    assert context.object_id == "OBJ-001"


def test_bad_jwt_never_falls_back_to_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    _reject("legacy.actor/INSPECTOR.bad")
