"""Verified JWT authentication and explicit local-development compatibility."""

from __future__ import annotations

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
def rsa_keys() -> tuple[rsa.RSAPrivateKey, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


def _public_pem(key: object) -> str:
    return key.public_bytes(  # type: ignore[attr-defined, no-any-return]
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def _private_pem(key: object) -> str:
    return key.private_bytes(  # type: ignore[attr-defined, no-any-return]
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    public: str,
    algorithm: str = "RS256",
) -> None:
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
        "nbf": (now - timedelta(seconds=1)).timestamp(),
        "exp": (now + timedelta(minutes=5)).timestamp(),
    }
    claims.update(changes)
    return claims


def _token(
    private: object,
    algorithm: str = "RS256",
    **changes: object,
) -> str:
    return jwt.encode(_claims(**changes), private, algorithm=algorithm)


def _reject(token: str | None) -> None:
    with pytest.raises(AuthenticationRequiredError, match="^authentication required$"):
        parse_bearer(None if token is None else f"Bearer {token}")


def test_valid_signed_rsa_jwt(
    rsa_keys: tuple[rsa.RSAPrivateKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, public = rsa_keys
    _configure(monkeypatch, public)
    context = parse_bearer(f"Bearer {_token(private)}")
    assert context.subject == "insp-7"
    assert context.roles == ("INSPECTOR",)
    assert context.object_id == "OBJ-001"


def test_valid_signed_es256_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    private = ec.generate_private_key(ec.SECP256R1())
    _configure(monkeypatch, _public_pem(private.public_key()), "ES256")
    context = parse_bearer(f"Bearer {_token(private, 'ES256')}")
    assert context.subject == "insp-7"


@pytest.mark.parametrize("name", ["exp", "nbf"])
@pytest.mark.parametrize("value", [True, False, "1", None, [], {}])
def test_numeric_dates_reject_non_numbers(
    name: str,
    value: object,
    rsa_keys: tuple[rsa.RSAPrivateKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, public = rsa_keys
    _configure(monkeypatch, public)
    _reject(_token(private, **{name: value}))


def test_numeric_dates_accept_int_and_float(
    rsa_keys: tuple[rsa.RSAPrivateKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private, public = rsa_keys
    _configure(monkeypatch, public)
    now = datetime.now(UTC).timestamp()
    context = parse_bearer(
        f"Bearer {_token(private, nbf=int(now) - 1, exp=now + 300.5)}"
    )
    assert context.subject == "insp-7"


@pytest.mark.parametrize(
    ("configured_algorithm", "key_pem"),
    [
        ("RS256", "private"),
        ("RS256", "ec"),
        ("ES256", "rsa"),
        ("ES256", "wrong-curve"),
    ],
)
def test_invalid_verification_key_is_fail_closed(
    configured_algorithm: str,
    key_pem: str,
    rsa_keys: tuple[rsa.RSAPrivateKey, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rsa_private, rsa_public = rsa_keys
    ec_private = ec.generate_private_key(ec.SECP256R1())
    values = {
        "private": _private_pem(rsa_private),
        "ec": _public_pem(ec_private.public_key()),
        "rsa": rsa_public,
        "wrong-curve": _public_pem(
            ec.generate_private_key(ec.SECP384R1()).public_key()
        ),
    }
    _configure(monkeypatch, values[key_pem], configured_algorithm)
    _reject(_token(rsa_private))


@pytest.mark.parametrize(
    "token",
    [
        "a",
        "a.b",
        "a.b.c",
        "a.b.c.d",
        "prefix.insp-7@OBJ-001/INSPECTOR",
        "insp-7@OBJ-001/INSPECTOR.suffix",
    ],
)
def test_every_dotted_token_uses_jwt_validation(
    token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    _reject(token)


@pytest.mark.parametrize(
    "token",
    [
        "insp-7@OBJ-001/INSPECTOR/ADMIN",
        "insp-7@OBJ-001/INSPECTOR,",
        "insp 7@OBJ-001/INSPECTOR",
        "insp-7@OBJ-001/inspector",
        "@OBJ-001/INSPECTOR",
    ],
)
def test_ambiguous_legacy_grammar_is_rejected(
    token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
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
