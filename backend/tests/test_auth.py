"""Временный Bearer-контракт: object scope обязателен для объектного API."""

from __future__ import annotations

import pytest

from kontur.presentation.auth import parse_bearer
from kontur.presentation.rbac import AuthenticationRequiredError


def test_scoped_token_separates_subject_object_and_roles() -> None:
    context = parse_bearer("Bearer insp-7@OBJ-001/INSPECTOR,SUPERVISOR")
    assert context.subject == "insp-7"
    assert context.object_id == "OBJ-001"
    assert context.roles == ("INSPECTOR", "SUPERVISOR")


def test_unscoped_token_remains_valid_only_for_non_object_operations() -> None:
    context = parse_bearer("Bearer ADMIN")
    assert context.subject == "ADMIN"
    assert context.object_id is None
    assert context.roles == ("ADMIN",)


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "Basic value",
        "Bearer ",
        "Bearer @OBJ-001/INSPECTOR",
        "Bearer insp-7@/INSPECTOR",
    ],
)
def test_malformed_token_is_rejected(token: str | None) -> None:
    with pytest.raises(AuthenticationRequiredError):
        parse_bearer(token)
