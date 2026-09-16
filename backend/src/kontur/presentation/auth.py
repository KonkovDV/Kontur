"""Разбор Bearer-токена. Пока нет OIDC, токен — это субъект и роли, не JWT.

Формат: `Bearer <actor_id>/<ROLE>[,<ROLE>]`. Пример: `insp-7/INSPECTOR`.
Короткая форма `Bearer INSPECTOR` — субъект совпадает с ролью (для тестов).
Пустой заголовок — 401. Неизвестные имена ролей не повышают права.
"""

from __future__ import annotations

from kontur.domain.state_machines import Actor
from kontur.presentation.rbac import AuthenticationRequiredError, Role


def parse_bearer(authorization: str | None) -> tuple[str, tuple[str, ...]]:
    if authorization is None or not authorization.lower().startswith("bearer "):
        raise AuthenticationRequiredError("нет заголовка Authorization")
    payload = authorization[7:].strip()
    if not payload:
        raise AuthenticationRequiredError("пустой Bearer-токен")
    if "/" in payload:
        subject, _, roles_part = payload.partition("/")
    else:
        subject, roles_part = payload, payload
    subject = subject.strip()
    roles = tuple(part.strip() for part in roles_part.split(",") if part.strip())
    if not subject or not roles:
        raise AuthenticationRequiredError("токен без субъекта или роли")
    return subject, roles


def actor_from_roles(subject: str, roles: frozenset[Role]) -> Actor:
    """Все роли п. 12 — люди. Машина токен не получает."""

    return Actor(
        actor_id=subject,
        is_human=True,
        is_supervisor=Role.SUPERVISOR in roles,
    )
