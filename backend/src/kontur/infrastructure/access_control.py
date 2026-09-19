"""Fail-closed контроль доступа к объектам (ТЗ §9.1, RT-H)."""

from __future__ import annotations

__all__ = ["AccessDeniedError", "check_object_access"]


class AccessDeniedError(PermissionError):
    """Попытка доступа без object scope или к чужому объекту."""

    def __init__(self, *, requested: str | None, caller: str | None) -> None:
        requested_label = requested if requested is not None else "<unassigned>"
        caller_label = caller if caller is not None else "<missing-scope>"
        super().__init__(
            f"Access to object '{requested_label}' denied for caller '{caller_label}'"
        )
        self.requested_object_id = requested
        self.caller_object_id = caller


def check_object_access(
    *,
    requested_object_id: str | None,
    caller_object_id: str | None,
) -> None:
    """Разрешить только точное совпадение непустых object_id.

    Системный код, которому нужен глобальный доступ, не должен маскироваться
    отсутствующим scope и обязан использовать отдельный доверенный путь.
    HTTP-запрос без scope закрывается по умолчанию.
    """

    if (
        requested_object_id is not None
        and caller_object_id is not None
        and requested_object_id == caller_object_id
    ):
        return
    raise AccessDeniedError(
        requested=requested_object_id,
        caller=caller_object_id,
    )
