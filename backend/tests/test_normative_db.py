"""Тесты нормативной базы данных (RT-E, RT-F, ТЗ §9.2)."""

from __future__ import annotations

from datetime import date

import pytest

from kontur.infrastructure.normative_db import (
    NormativeDB,
    NormativeRevision,
    NormativeStatus,
    is_revision_expired,
)

# ── вспомогательные фабрики ───────────────────────────────────────────────────


def _rev(
    norm_id: str = "SP-001",
    revision: str = "2016",
    effective_from: date = date(2016, 1, 1),
    expiry_date: date | None = None,
    is_signed: bool = True,
    document_hash: str = "a" * 64,
) -> NormativeRevision:
    return NormativeRevision(
        norm_id=norm_id,
        revision=revision,
        effective_from=effective_from,
        expiry_date=expiry_date,
        document_hash=document_hash,
        is_signed=is_signed,
    )


# ── is_revision_expired ──────────────────────────────────────────────────────


def test_not_expired_when_no_expiry_date() -> None:
    """Действующая редакция (expiry=None) не истекает никогда."""
    rev = _rev(expiry_date=None)
    assert not is_revision_expired(rev, date(2099, 1, 1))


def test_not_expired_on_expiry_day() -> None:
    """Дата истечения включительна: в сам день ещё действует."""
    rev = _rev(expiry_date=date(2023, 12, 31))
    assert not is_revision_expired(rev, date(2023, 12, 31))


def test_expired_after_expiry_day() -> None:
    """После даты истечения — редакция истекла."""
    rev = _rev(expiry_date=date(2023, 12, 31))
    assert is_revision_expired(rev, date(2024, 1, 1))


# ── RT-E: expired revision ───────────────────────────────────────────────────


def test_rt_e_expired_revision_returns_expired_status() -> None:
    """Истёкшая норма → EXPIRED, revision=None. (RT-E)"""
    db = NormativeDB([_rev(expiry_date=date(2020, 12, 31))])
    result = db.get_valid_revision("SP-001", as_of=date(2021, 1, 1))
    assert result.status == NormativeStatus.EXPIRED
    assert result.revision is None  # не используется как эталон


def test_valid_revision_returns_valid_status() -> None:
    """Действующая подписанная → VALID."""
    db = NormativeDB([_rev(expiry_date=None)])
    result = db.get_valid_revision("SP-001", as_of=date(2021, 1, 1))
    assert result.status == NormativeStatus.VALID
    assert result.revision is not None


# ── RT-F: unsigned chunk ──────────────────────────────────────────────────


def test_rt_f_unsigned_revision_returns_not_signed() -> None:
    """Неподписанная норма → NOT_SIGNED, revision=None. (RT-F)"""
    db = NormativeDB([_rev(is_signed=False)])
    result = db.get_valid_revision("SP-001", as_of=date(2021, 1, 1))
    assert result.status == NormativeStatus.NOT_SIGNED
    assert result.revision is None  # не попадает в правило


def test_get_revision_unsigned_returns_not_signed() -> None:
    """get_revision также отклоняет неподписанную."""
    db = NormativeDB([_rev(is_signed=False)])
    result = db.get_revision("SP-001", "2016")
    assert result.status == NormativeStatus.NOT_SIGNED


def test_unsigned_allowed_when_not_required() -> None:
    """Если require_signed=False — неподписанная проходит."""
    db = NormativeDB([_rev(is_signed=False)])
    result = db.get_valid_revision(
        "SP-001", as_of=date(2021, 1, 1), require_signed=False
    )
    assert result.status == NormativeStatus.VALID


# ── общие случаи ─────────────────────────────────────────────────────────────


def test_not_found_returns_not_found_status() -> None:
    db = NormativeDB([])
    assert db.get_valid_revision("SP-999", as_of=date(2021, 1, 1)).status == NormativeStatus.NOT_FOUND
    assert db.get_revision("SP-999", "2016").status == NormativeStatus.NOT_FOUND


def test_latest_revision_selected_by_effective_from() -> None:
    """Из нескольких редакций выбирается последняя по дате ввода."""
    old = _rev(revision="2012", effective_from=date(2012, 1, 1))
    new = _rev(revision="2016", effective_from=date(2016, 1, 1))
    db = NormativeDB([old, new])
    result = db.get_valid_revision("SP-001", as_of=date(2020, 1, 1))
    assert result.status == NormativeStatus.VALID
    assert result.revision is not None
    assert result.revision.revision == "2016"


@pytest.mark.parametrize(
    "expiry, as_of, expected",
    [
        (None, date(2099, 1, 1), NormativeStatus.VALID),
        (date(2020, 12, 31), date(2020, 12, 31), NormativeStatus.VALID),  # включительно
        (date(2020, 12, 31), date(2021, 1, 1), NormativeStatus.EXPIRED),
    ],
)
def test_expiry_boundary_cases(
    expiry: date | None, as_of: date, expected: NormativeStatus
) -> None:
    db = NormativeDB([_rev(expiry_date=expiry)])
    assert db.get_valid_revision("SP-001", as_of=as_of).status == expected
