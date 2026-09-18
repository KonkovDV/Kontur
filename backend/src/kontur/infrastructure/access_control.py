"""Контроль доступа к объектам (ТЗ §9.1, RT-H).

Мотивация
---------
Система обслуживает несколько строительных объектов (организаций). Каждый
файл/паспорт принадлежит ровно одному объекту (фильд `object_id`
в `DocumentPassport`). Инспектор видит только файлы своего объекта.

Oracle RT-H:
  «Запрос к чужому объекту отклоняется и не оставляет побочного эффекта.»

Гарантии
--------
- `check_object_access()` — чистая функция (pure function).
  Нет IO, нет побочных эффектов — при отказе ничего не записывается.
- Толькое возможное исключение — `AccessDeniedError`.
- `None` object_id значает «объект не назначен» → доступ разрешён всем.

Интеграция
---------
  HTTP-обработчик до обращения к кэшу/БД:
  ```python
  check_object_access(
      requested_object_id=passport.object_id,
      caller_object_id=current_user.object_id,
  )
  # Если прошло — доступ разрешён, иначе AccessDeniedError → HTTP 403
  ```

Ссылки
------
  docs/RED_TEAM.md  — RT-H (multi-tenancy)
  ТЗ §9.1           — разделение данных по объектам
"""
from __future__ import annotations

__all__ = ["AccessDeniedError", "check_object_access"]


class AccessDeniedError(PermissionError):
    """Попытка межобъектного доступа.

    Атрибуты позволяют HTTP-слою сформировать 403 с подробностями.
    """

    def __init__(self, *, requested: str, caller: str) -> None:
        super().__init__(
            f"Access to object '{requested}' denied for caller '{caller}'"
        )
        #: object_id, к которому запрашивали доступ
        self.requested_object_id: str = requested
        #: object_id инициатора запроса
        self.caller_object_id: str = caller


def check_object_access(
    *,
    requested_object_id: str | None,
    caller_object_id: str | None,
) -> None:
    """Проверить, имеет ли caller доступ к requested_object_id.

    Чистая функция (pure): нет IO, нет побочных эффектов.
    При отказе ничего не записывается в БД и не изменяется кэш.

    Правила:
      - ``None`` в любом аргументе = «не назначен» → доступ разрешён.
      - Совпадение object_id → доступ разрешён.
      - Несовпадение ненулевых object_id → :exc:`AccessDeniedError`.

    Args:
        requested_object_id: object_id файла/паспорта, к которому запрашивают доступ.
            ``None`` если файл не привязан к объекту.
        caller_object_id: object_id инициатора запроса (организация/инспектор).
            ``None`` если caller не привязан к объекту (например, системный процесс).

    Raises:
        AccessDeniedError: если caller пытается получить доступ к чужому object_id.
    """
    # None — неназначенный объект: доступ разрешён всем
    if requested_object_id is None or caller_object_id is None:
        return
    # Совпадение — доступ разрешён
    if requested_object_id == caller_object_id:
        return
    # Несовпадение ненулевых — отказ, нет ио, нет побочных эффектов
    raise AccessDeniedError(
        requested=requested_object_id,
        caller=caller_object_id,
    )
