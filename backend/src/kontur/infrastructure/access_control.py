"""Fail-closed object access control (TZ §9.1, RT-H)."""

from __future__ import annotations

__all__ = ["AccessDeniedError", "check_object_access"]


class AccessDeniedError(PermissionError):
    """Object scope is absent or does not match."""

    def __init__(self, *, requested: str | None, caller: str | None) -> None:
        # Keep identifiers available to trusted in-process diagnostics, but never put
        # them in the exception text returned by the API.
        super().__init__("access denied")
        self.requested_object_id = requested
        self.caller_object_id = caller


def check_object_access(
    *,
    requested_object_id: str | None,
    caller_object_id: str | None,
) -> None:
    """Allow only an exact match between two non-empty object identifiers."""

    if (
        requested_object_id is not None
        and caller_object_id is not None
        and requested_object_id == caller_object_id
    ):
        return
    raise AccessDeniedError(requested=requested_object_id, caller=caller_object_id)
