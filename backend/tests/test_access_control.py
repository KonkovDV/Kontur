"""Тесты контроля доступа к объектам (RT-H, ТЗ §9.1)."""

from __future__ import annotations

import pytest

from kontur.infrastructure.access_control import AccessDeniedError, check_object_access

# ── разрешенные случаи ─────────────────────────────────────────────────────


def test_same_object_id_is_allowed() -> None:
    """Совпадение object_id → доступ разрешён, нет исключений."""
    check_object_access(requested_object_id="OBJ-001", caller_object_id="OBJ-001")


def test_requested_none_is_allowed() -> None:
    """Неназначенный объект → доступен всем."""
    check_object_access(requested_object_id=None, caller_object_id="OBJ-001")
    check_object_access(requested_object_id=None, caller_object_id=None)


def test_caller_none_is_allowed() -> None:
    """Неназначенный caller (системный процесс) → доступен."""
    check_object_access(requested_object_id="OBJ-001", caller_object_id=None)


# ── запрещённые случаи ────────────────────────────────────────────────────


def test_different_object_ids_raise_access_denied_error() -> None:
    """Несовпадение ненулевых object_id → AccessDeniedError."""
    with pytest.raises(AccessDeniedError):
        check_object_access(
            requested_object_id="OBJ-B",
            caller_object_id="OBJ-A",
        )


def test_access_denied_error_carries_both_ids() -> None:
    """Ошибка содержит оба object_id для HTTP 403 ответа."""
    with pytest.raises(AccessDeniedError) as exc_info:
        check_object_access(
            requested_object_id="PROJ-XYZ",
            caller_object_id="PROJ-ABC",
        )
    err = exc_info.value
    assert err.requested_object_id == "PROJ-XYZ"
    assert err.caller_object_id == "PROJ-ABC"


def test_access_denied_is_subclass_of_permission_error() -> None:
    """Иерархия: AccessDeniedError ⊂ PermissionError → FastAPI даст HTTP 403."""
    with pytest.raises(PermissionError):
        check_object_access(
            requested_object_id="OBJ-X",
            caller_object_id="OBJ-Y",
        )


# ── чистая функция: без побочных эффектов ────────────────────────────


def test_pure_function_repeated_calls_are_idempotent() -> None:
    """Множество вызовов не накапливают состояние (pure function)."""
    for _ in range(5):
        check_object_access(
            requested_object_id="OBJ-001",
            caller_object_id="OBJ-001",
        )
    for _ in range(5):
        with pytest.raises(AccessDeniedError):
            check_object_access(
                requested_object_id="OBJ-X",
                caller_object_id="OBJ-Y",
            )


def test_cross_object_denied_regardless_of_similarity() -> None:
    """Любое несовпадение — отказ. Похожие названия не дают доступ."""
    cases = [
        ("OBJ-001", "OBJ-002"),
        ("OBJ-001", "OBJ-0011"),  # префиксное совпадение
        ("OBJ-001", "obj-001"),  # регистр значим
        ("A", "B"),
        ("\u043eбъ-001", "OBJ-001"),  # рус/лат — разные
    ]
    for req, caller in cases:
        with pytest.raises(AccessDeniedError, match=req):
            check_object_access(
                requested_object_id=req,
                caller_object_id=caller,
            )


def test_error_message_contains_both_ids() -> None:
    """str(err) содержит оба ID для логирования."""
    with pytest.raises(AccessDeniedError) as exc_info:
        check_object_access(
            requested_object_id="TARGET",
            caller_object_id="ATTACKER",
        )
    msg = str(exc_info.value)
    assert "TARGET" in msg
    assert "ATTACKER" in msg


@pytest.mark.parametrize(
    "req, caller",
    [
        (None, None),
        (None, "OBJ-001"),
        ("OBJ-001", None),
        ("OBJ-001", "OBJ-001"),
    ],
)
def test_allowed_combinations_return_none(
    req: str | None, caller: str | None
) -> None:
    """Все разрешённые комбинации возвращают None (чистая функция)."""
    result = check_object_access(
        requested_object_id=req, caller_object_id=caller
    )
    assert result is None
