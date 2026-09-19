"""Authentication boundary: verified JWT by default, opt-in legacy tokens for local dev."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from kontur.domain.state_machines import Actor
from kontur.presentation.rbac import AuthenticationRequiredError, Role

_AUTHENTICATION_REQUIRED = "authentication required"
_ALLOWED_ALGORITHMS = frozenset({"RS256", "ES256"})
_LEGACY_TOKEN = re.compile(
    r"(?:[A-Za-z0-9_-]+(?:@[A-Za-z0-9_-]+)?/"
    r"[A-Z][A-Z0-9_]*(?:,[A-Z][A-Z0-9_]*)*|[A-Z][A-Z0-9_]*)\Z"
)


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: str
    roles: tuple[str, ...]
    object_id: str | None


def _authentication_required() -> AuthenticationRequiredError:
    return AuthenticationRequiredError(_AUTHENTICATION_REQUIRED)


def _is_true(value: str | None) -> bool:
    return value is not None and value.lower() == "true"


def _legacy_context(token: str) -> AuthContext:
    if _LEGACY_TOKEN.fullmatch(token) is None:
        raise _authentication_required()
    if "/" in token:
        principal, roles_part = token.split("/", maxsplit=1)
    else:
        principal, roles_part = token, token
    roles = tuple(roles_part.split(","))
    if "@" in principal:
        subject, object_id = principal.split("@", maxsplit=1)
    else:
        subject = principal
        object_id = None
    return AuthContext(subject=subject, roles=roles, object_id=object_id)


def _verification_key(public_key_pem: str, algorithm: str) -> object:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise _authentication_required() from exc
    if algorithm == "RS256" and isinstance(key, rsa.RSAPublicKey):
        return key
    if (
        algorithm == "ES256"
        and isinstance(key, ec.EllipticCurvePublicKey)
        and isinstance(key.curve, ec.SECP256R1)
    ):
        return key
    raise _authentication_required()


def _numeric_date(claims: dict[str, Any], name: str) -> None:
    value = claims.get(name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise _authentication_required()


def _validated_claims(token: str) -> dict[str, Any]:
    algorithm = os.environ.get("KONTUR_JWT_ALGORITHM", "RS256").strip()
    issuer = os.environ.get("KONTUR_JWT_ISSUER", "").strip()
    audience = os.environ.get("KONTUR_JWT_AUDIENCE", "").strip()
    public_key_pem = (
        os.environ.get("KONTUR_JWT_PUBLIC_KEY", "").replace("\\n", "\n").strip()
    )
    if algorithm not in _ALLOWED_ALGORITHMS or not issuer or not audience or not public_key_pem:
        raise _authentication_required()
    key = _verification_key(public_key_pem, algorithm)

    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != algorithm:
            raise _authentication_required()
        decoded = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            issuer=issuer,
            audience=audience,
            options={
                "require": ["exp", "nbf", "iss", "aud", "sub", "roles"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iss": True,
                "verify_aud": True,
                "strict_aud": True,
            },
        )
    except AuthenticationRequiredError:
        raise
    except (jwt.PyJWTError, TypeError, ValueError, KeyError) as exc:
        raise _authentication_required() from exc
    if not isinstance(decoded, dict):
        raise _authentication_required()
    claims: dict[str, Any] = decoded
    _numeric_date(claims, "exp")
    _numeric_date(claims, "nbf")
    return claims


def _jwt_context(token: str) -> AuthContext:
    claims = _validated_claims(token)
    subject = claims.get("sub")
    roles = claims.get("roles")
    object_id = claims.get("object_id")
    if not isinstance(subject, str) or not subject.strip():
        raise _authentication_required()
    if (
        not isinstance(roles, list)
        or not roles
        or any(not isinstance(role, str) or not role.strip() for role in roles)
    ):
        raise _authentication_required()
    if object_id is not None and (
        not isinstance(object_id, str) or not object_id.strip()
    ):
        raise _authentication_required()
    return AuthContext(
        subject=subject.strip(),
        roles=tuple(role.strip() for role in roles),
        object_id=object_id.strip() if isinstance(object_id, str) else None,
    )


def parse_bearer(authorization: str | None) -> AuthContext:
    try:
        if authorization is None or not authorization.lower().startswith("bearer "):
            raise _authentication_required()
        token = authorization[7:].strip()
        if not token:
            raise _authentication_required()
        # Every dotted token is JWT-shaped input. It must never reach legacy parsing,
        # including one/two/four-part, truncated, prefixed, or suffixed variants.
        if "." in token:
            return _jwt_context(token)
        if _is_true(os.environ.get("KONTUR_ALLOW_INSECURE_DEV_AUTH")):
            return _legacy_context(token)
        raise _authentication_required()
    except AuthenticationRequiredError:
        raise
    except Exception as exc:
        raise _authentication_required() from exc


def actor_from_roles(subject: str, roles: frozenset[Role]) -> Actor:
    """All RBAC roles represent humans; machine credentials are not issued here."""

    return Actor(
        actor_id=subject,
        is_human=True,
        is_supervisor=Role.SUPERVISOR in roles,
    )
