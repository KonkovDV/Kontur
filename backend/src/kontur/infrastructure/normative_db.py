"""Нормативная база данных редакций (ТЗ §9.2, RT-E, RT-F).

Мотивация
---------
Нормативная база хранит редакции нормативных документов (СП, ГОСТ, СНиП и т.п.).
Каждая редакция идентифицируется SHA-256 источника и флагом подписи.

Oracle RT-E:
  «Истёкшая редакция нормы не даёт нарушения, только CLARIFICATION_REQUIRED.»
  Истёкшая редакция не может быть эталоном сравнения. Результат: EXPIRED,
  приложение преобразует в CLARIFICATION_REQUIRED.

Oracle RT-F:
  «Неподписанный нормативный фрагмент не попадает в исполнение правила.»
  Без верифицированной подписи редакция отклоняется с NOT_SIGNED.

Гарантии
--------
- Все операции — чистые функции (pure): нет IO, нет побочных эффектов.
- Источник каждой редакции идентифицируется SHA-256 (ADR-0002).
- Истёкшая редакция никогда не возвращается как VALID.
- Неподписанная редакция не используется как эталон при require_signed=True.

Ссылки
------
  docs/RED_TEAM.md  — RT-E, RT-F
  ТЗ §9.2          — нормативный реестр
  ADR-0002          — привязка источников по SHA-256
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum, auto
from typing import Optional

__all__ = [
    "NormativeRevision",
    "NormativeDB",
    "NormativeStatus",
    "NormativeResult",
    "is_revision_expired",
]


class NormativeStatus(Enum):
    """Статус нормативной редакции при запросе."""
    VALID = auto()        # Редакция действует и подписана
    EXPIRED = auto()      # Редакция истекла → CLARIFICATION_REQUIRED
    NOT_SIGNED = auto()   # Нет подписи → не используется
    NOT_FOUND = auto()    # Норма не найдена


@dataclass(frozen=True)
class NormativeRevision:
    """Одна редакция нормативного документа.

    Attributes:
        norm_id:        Идентификатор нормы (например «СП 20.13330.2016»).
        revision:       Обозначение редакции (год или код).
        effective_from: Дата ввода в действие.
        expiry_date:    Дата окончания действия. None = действует.
        document_hash:  SHA-256 файла источника (ADR-0002, неизменяемая привязка).
        is_signed:      True, если файл имеет верифицированную подпись.
    """

    norm_id: str
    revision: str
    effective_from: date
    expiry_date: Optional[date]  # None — редакция действует
    document_hash: str           # SHA-256 источника
    is_signed: bool              # Подтверждённая подпись


@dataclass(frozen=True)
class NormativeResult:
    """Результат запроса к нормативной базе.

    При status != VALID, revision равно None (не используется как эталон).
    """

    status: NormativeStatus
    revision: Optional[NormativeRevision]


def is_revision_expired(revision: NormativeRevision, as_of: date) -> bool:
    """Истекла ли редакция к дате ``as_of``.

    Чистая функция: нет IO, нет побочных эффектов.
    """
    if revision.expiry_date is None:
        return False
    # Дата истечения включительна: в саму день expiry ещё действует
    return as_of > revision.expiry_date


class NormativeDB:
    """Хранилище нормативных редакций без IO.

    Загружается при старте из YAML/JSON-реестра.
    Все методы возвращают NormativeResult: инициатор запроса обязан
    проверить status и ответить CLARIFICATION_REQUIRED при
    EXPIRED/NOT_SIGNED/NOT_FOUND.
    """

    def __init__(self, revisions: list[NormativeRevision]) -> None:
        # Ключ = (norm_id, revision)
        self._revisions: dict[tuple[str, str], NormativeRevision] = {
            (r.norm_id, r.revision): r for r in revisions
        }

    def get_revision(
        self, norm_id: str, revision: str
    ) -> NormativeResult:
        """Найти конкретную редакцию (без проверки дат).

        Returns:
            NormativeResult(VALID|NOT_SIGNED|NOT_FOUND, revision|None)
        """
        rev = self._revisions.get((norm_id, revision))
        if rev is None:
            return NormativeResult(NormativeStatus.NOT_FOUND, None)
        if not rev.is_signed:
            return NormativeResult(NormativeStatus.NOT_SIGNED, None)
        return NormativeResult(NormativeStatus.VALID, rev)

    def get_valid_revision(
        self,
        norm_id: str,
        *,
        as_of: date,
        require_signed: bool = True,
    ) -> NormativeResult:
        """Найти актуальную подписанную редакцию на дату ``as_of``.

        Правила (RT-E, RT-F):
          - Нет редакций → NOT_FOUND.
          - Истёкшая последняя редакция → EXPIRED (RT-E: CLARIFICATION_REQUIRED).
          - Неподписанная (если require_signed) → NOT_SIGNED (RT-F: не используется).
          - Действующая и подписанная → VALID.

        Args:
            norm_id:       Идентификатор нормы.
            as_of:         Дата проверки (обычно: дата загрузки документа).
            require_signed: Если True (по умолчанию), неподписанная редакция вернёт
                           NOT_SIGNED (вместо невалидных данных).

        Returns:
            NormativeResult с status и revision (None при не-VALID).
        """
        candidates = [
            r for r in self._revisions.values()
            if r.norm_id == norm_id
        ]
        if not candidates:
            return NormativeResult(NormativeStatus.NOT_FOUND, None)

        # Выбираем последнюю редакцию по дате ввода
        candidates.sort(key=lambda r: r.effective_from, reverse=True)
        latest = candidates[0]

        # RT-E: истёкшая редакция → EXPIRED, не нарушение
        if is_revision_expired(latest, as_of):
            return NormativeResult(NormativeStatus.EXPIRED, None)

        # RT-F: неподписанная → NOT_SIGNED, не используется
        if require_signed and not latest.is_signed:
            return NormativeResult(NormativeStatus.NOT_SIGNED, None)

        return NormativeResult(NormativeStatus.VALID, latest)
