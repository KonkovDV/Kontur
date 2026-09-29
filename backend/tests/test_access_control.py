"""Тесты fail-closed контроля доступа к объектам (RT-H, ТЗ §9.1)."""

from __future__ import annotations

import pytest

from kontur.infrastructure.access_control import AccessDeniedError, check_object_access


def test_same_non_empty_object_id_is_allowed() -> None:
    check_object_access(requested_object_id="OBJ-001", caller_object_id="OBJ-001")


@pytest.mark.parametrize(
    ("requested", "caller"),
    [
        (None, None),
        (None, "OBJ-001"),
        ("OBJ-001", None),
        ("OBJ-B", "OBJ-A"),
        ("OBJ-001", "OBJ-0011"),
        ("OBJ-001", "obj-001"),
        ("объ-001", "OBJ-001"),
    ],
)
def test_missing_or_different_scope_is_denied(
    requested: str | None,
    caller: str | None,
) -> None:
    with pytest.raises(AccessDeniedError) as exc_info:
        check_object_access(
            requested_object_id=requested,
            caller_object_id=caller,
        )
    assert exc_info.value.requested_object_id == requested
    assert exc_info.value.caller_object_id == caller


def test_denial_is_a_permission_error_and_has_no_state() -> None:
    for _ in range(5):
        with pytest.raises(PermissionError):
            check_object_access(
                requested_object_id="OBJ-X",
                caller_object_id="OBJ-Y",
            )
    check_object_access(requested_object_id="OBJ-X", caller_object_id="OBJ-X")
