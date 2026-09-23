"""Матрица прав ТЗ п. 12: operationId → роли, которым операция разрешена.

Единственный источник истины сразу для двух мест: `x-required-roles` в
`contracts/openapi.yaml` и проверка прав в обработчиках. Расхождение контракта
и кода ловит `scripts/check_contracts.py`, поэтому «забыть роль» нельзя.

ADR-0001: юридическое решение принимает инспектор. Поэтому администратор
системы не может ни подтвердить нарушение, ни финализировать протокол, ни
отменить финализацию — его роли нет ни в одной из этих строк. Отмена
финализации — только супервизор (ТЗ п. 9.3).

Неизвестная роль не даёт прав: матрица работает по принципу «разрешено только
перечисленное», а незнакомая операция — ошибка конфигурации, а не свободный
доступ.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    """Роли ТЗ п. 12."""

    INSPECTOR = "INSPECTOR"
    SUPERVISOR = "SUPERVISOR"
    ADMIN = "ADMIN"


class AuthenticationRequiredError(PermissionError):
    """Субъекта нет: отвечаем 401, а не 403."""


class PermissionDeniedError(PermissionError):
    """Субъект есть, прав не хватает: 403."""


HTTP_UNAUTHORIZED: int = 401
HTTP_FORBIDDEN: int = 403

#: operationId из OpenAPI → роли. Пустое множество запрещено по построению.
REQUIRED_ROLES: dict[str, frozenset[Role]] = {
    "uploadDocuments": frozenset({Role.INSPECTOR, Role.SUPERVISOR}),
    "getSystemCapabilities": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "getProcessStatus": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "getProcessDocuments": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "listProcessFindings": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "getFilePagePng": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "getProtocol": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "getAuditLog": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "getEvidenceCard": frozenset({Role.INSPECTOR, Role.SUPERVISOR, Role.ADMIN}),
    "reviewFinding": frozenset({Role.INSPECTOR, Role.SUPERVISOR}),
    "startVerification": frozenset({Role.INSPECTOR, Role.SUPERVISOR}),
    "completeVerification": frozenset({Role.INSPECTOR, Role.SUPERVISOR}),
    "finalizeProtocol": frozenset({Role.INSPECTOR, Role.SUPERVISOR}),
    "unfinalizeProtocol": frozenset({Role.SUPERVISOR}),
    "selectRevision": frozenset({Role.INSPECTOR, Role.SUPERVISOR}),
    "syncInspection": frozenset({Role.SUPERVISOR, Role.ADMIN}),
}

#: Операции, создающие или отменяющие юридическое решение (ADR-0001).
LEGAL_DECISION_OPERATIONS: frozenset[str] = frozenset(
    {"reviewFinding", "finalizeProtocol", "unfinalizeProtocol", "selectRevision"}
)


def roles_for(operation_id: str) -> frozenset[Role]:
    """Роли операции. Неописанная операция — ошибка конфигурации, а не доступ."""

    try:
        return REQUIRED_ROLES[operation_id]
    except KeyError as exc:
        raise ValueError(f"операция {operation_id!r} не описана в матрице прав ТЗ п. 12") from exc


def authorize(operation_id: str, roles: Iterable[str | Role]) -> frozenset[Role]:
    """Вернуть пересечение ролей субъекта и операции либо поднять 401/403."""

    allowed = roles_for(operation_id)
    presented = list(roles)
    if not presented:
        raise AuthenticationRequiredError(f"{operation_id}: запрос без роли субъекта")

    recognized: set[Role] = set()
    for role in presented:
        try:
            recognized.add(Role(role))
        except ValueError:
            continue

    granted = allowed & recognized
    if not granted:
        names = ", ".join(sorted(member.value for member in allowed))
        raise PermissionDeniedError(f"{operation_id}: требуется одна из ролей {names}")
    return frozenset(granted)
