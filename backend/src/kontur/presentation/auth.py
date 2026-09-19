"""Разбор временного Bearer-токена до подключения OIDC.

Формат для объектных операций: ``Bearer <actor_id>@<object_id>/<ROLE>[,<ROLE>]``.
Пример: ``Bearer insp-7@OBJ-001/INSPECTOR``. Токен без ``@object_id`` допустим
только для необъектных операций (например, capabilities); объектный API
проверяет scope отдельно и закрывается по умолчанию.
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.domain.state_machines import Actor
from kontur.presentation.rbac import AuthenticationRequiredError, Role


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: str
    roles: tuple[str, ...]
    object_id: str | None


def parse_bearer(authorization: str | None) -> AuthContext:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise AuthenticationRequiredError("нет заголовка Authorization")
    payload = authorization[7:].strip()
    if not payload:
        raise AuthenticationRequiredError("пустой Bearer-токен")
    if "/" in payload:
        principal, _, roles_part = payload.partition("/")
    else:
        principal, roles_part = payload, payload
    principal = principal.strip()
    roles = tuple(part.strip() for part in roles_part.split(",") if part.strip())
    if not principal or not roles:
        raise AuthenticationRequiredError("токен без субъекта или роли")

    if "@" in principal:
        subject, _, object_id = principal.rpartition("@")
        subject = subject.strip()
        object_id = object_id.strip()
        if not subject or not object_id:
            raise AuthenticationRequiredError("токен с пустым субъектом или object scope")
    else:
        subject = principal
        object_id = None
    return AuthContext(subject=subject, roles=roles, object_id=object_id)


def actor_from_roles(subject: str, roles: frozenset[Role]) -> Actor:
    """Все роли п. 12 — люди. Машина токен не получает."""

    return Actor(
        actor_id=subject,
        is_human=True,
        is_supervisor=Role.SUPERVISOR in roles,
    )
