"""Authentication boundary: verified JWT by default, opt-in legacy tokens for local dev."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import jwt

from kontur.domain.state_machines import Actor
from kontur.presentation.rbac import AuthenticationRequiredError, Role

_AUTHENTICATION_REQUIRED = "authentication required"
_ALLOWED_ALGORITHMS = frozenset({"RS256", "ES256"})


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: str
    roles: tuple[str, ...]
    object_id: str | None


def _authentication_required() -> AuthenticationRequiredError:
    # All malformed, missing, expired and unverifiable credentials cross the API
    # boundary as the same error. Never expose parser or crypto details to callers.
    return AuthenticationRequiredError(_AUTHENTICATION_REQUIRED)


def _is_true(value: str | None) -> bool:
    return value is not None and value.lower() == "true"


def _looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2


def _legacy_context(token: str) -> AuthContext:
    if "/" in token:
        principal, _, roles_part = token.partition("/")
    else:
        principal, roles_part = token, token
    principal = principal.strip()
    roles = tuple(part.strip() for part in roles_part.split(",") if part.strip())
    if not principal or not roles:
        raise _authentication_required()
    if "@" in principal:
        subject, _, object_id = principal.rpartition("@")
        subject = subject.strip()
        object_id = object_id.strip()
        if not subject or not object_id:
            raise _authentication_required()
    else:
        subject = principal
        object_id = None
    return AuthContext(subject=subject, roles=roles, object_id=object_id)


def _validated_claims(token: str) -> dict[str, Any]:
    algorithm = os.environ.get("KONTUR_JWT_ALGORITHM", "RS256").strip()
    issuer = os.environ.get("KONTUR_JWT_ISSUER", "").strip()
    audience = os.environ.get("KONTUR_JWT_AUDIENCE", "").strip()
    public_key = os.environ.get("KONTUR_JWT_PUBLIC_KEY", "").replace("\\n", "\n").strip()
    if algorithm not in _ALLOWED_ALGORITHMS or not issuer or not audience or not public_key:
        raise _authentication_required()

    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != algorithm:
            raise _authentication_required()
        claims = jwt.decode(
            token,
            public_key,
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
    if not isinstance(claims, dict):
        raise _authentication_required()
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
    if object_id is not None and (not isinstance(object_id, str) or not object_id.strip()):
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
        if _looks_like_jwt(token):
            # A bad JWT is always rejected; it can never downgrade to legacy auth.
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
