"""Матрица прав ТЗ п. 12: закрыто по умолчанию, администратор не судья."""

from __future__ import annotations

import pytest

from kontur.presentation.rbac import (
    LEGAL_DECISION_OPERATIONS,
    REQUIRED_ROLES,
    AuthenticationRequiredError,
    PermissionDeniedError,
    Role,
    authorize,
    roles_for,
)


def test_unknown_operation_fails_closed() -> None:
    with pytest.raises(ValueError, match="не описана"):
        roles_for("deleteEverything")
    with pytest.raises(ValueError):
        authorize("deleteEverything", [Role.ADMIN])


def test_request_without_subject_is_401_not_403() -> None:
    with pytest.raises(AuthenticationRequiredError):
        authorize("getProcessStatus", [])


def test_unknown_role_never_escalates() -> None:
    with pytest.raises(PermissionDeniedError):
        authorize("getProcessStatus", ["SUPERADMIN"])
    with pytest.raises(PermissionDeniedError):
        authorize("unfinalizeProtocol", ["inspector"])


def test_admin_cannot_make_or_revoke_a_legal_decision() -> None:
    for operation in sorted(LEGAL_DECISION_OPERATIONS):
        assert Role.ADMIN not in REQUIRED_ROLES[operation]
        with pytest.raises(PermissionDeniedError):
            authorize(operation, [Role.ADMIN])


def test_only_supervisor_unfinalizes() -> None:
    assert authorize("unfinalizeProtocol", [Role.SUPERVISOR]) == frozenset({Role.SUPERVISOR})
    with pytest.raises(PermissionDeniedError):
        authorize("unfinalizeProtocol", [Role.INSPECTOR])


def test_inspector_works_and_every_row_grants_someone() -> None:
    assert authorize("reviewFinding", [Role.INSPECTOR]) == frozenset({Role.INSPECTOR})
    assert authorize("selectRevision", [Role.INSPECTOR]) == frozenset({Role.INSPECTOR})
    assert authorize("startVerification", [Role.INSPECTOR]) == frozenset({Role.INSPECTOR})
    assert authorize("completeVerification", [Role.INSPECTOR]) == frozenset({Role.INSPECTOR})
    assert authorize("getAuditLog", [Role.ADMIN]) == frozenset({Role.ADMIN})
    assert authorize("uploadDocuments", ["INSPECTOR", "ADMIN"]) == frozenset({Role.INSPECTOR})
    with pytest.raises(PermissionDeniedError):
        authorize("startVerification", [Role.ADMIN])
    with pytest.raises(PermissionDeniedError):
        authorize("completeVerification", [Role.ADMIN])
    for operation, allowed in REQUIRED_ROLES.items():
        assert allowed, operation
        assert allowed <= set(Role)
