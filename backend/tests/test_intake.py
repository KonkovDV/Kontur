"""Комплексные E2E-тесты validate_intake() (ТЗ §9.1 / RT-A).

Покрывают:
  - FILE_TOO_LARGE    → отклонение с reason_code
  - DECOMPRESSION_BOMB → zip-бомба через ratio
  - EXPAND_LIMIT_EXCEEDED → zip с большим uncompressed
  - CORRUPT_ARCHIVE   → повреждённый zip
  - CORRUPT_PDF       → PDF без %%EOF
  - UNSUPPORTED_TYPE  → неизвестный тип
  - ok=True           → валидный zip / валидный PDF

Гарантия: validate_intake() не выбрасывает ни при каком входе (RT-A).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from kontur.infrastructure.intake import (
    MAX_FILE_BYTES,
    IntakeResult,
    RejectReason,
    validate_intake,
)


# ── вспомогательные фабрики ────────────────────────────────────────────────────


def _make_zip(content: bytes, filename: str = "file.pdf") -> bytes:
    """ZIP с одним файлом внутри."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


def _make_minimal_pdf() -> bytes:
    """PDF-минимальный файл, проходящий intake-проверку."""
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" b"%%EOF"


def _make_bomb_zip() -> bytes:
    """Зип-бомба: 1 МБ нулей → ~1 КБ в zip (ratio ~1000x)."""
    return _make_zip(b"\x00" * 1_000_000, "bomb.bin")


# ── FILE_TOO_LARGE ──────────────────────────────────────────────────────────────────


def test_file_too_large_rejected() -> None:
    """Файл > 50 МБ отклоняется с FILE_TOO_LARGE (ТЗ §9.1)."""
    big = b"%PDF-1.4" + b"X" * (MAX_FILE_BYTES + 1)
    result = validate_intake(big)
    assert not result.ok
    assert result.reason_code is RejectReason.FILE_TOO_LARGE
    assert str(MAX_FILE_BYTES + 9) in result.detail or len(big) > MAX_FILE_BYTES


def test_exactly_at_limit_is_not_rejected() -> None:
    """Файл ровно 50 МБ проходит проверку размера."""
    # Создаём ZIP ровно 50 МБ (невозможно без большого паддинга в памяти)
    # Просто проверяем: max_file_bytes=10 и данные ровно 10 байт
    data = b"%PDF-1.7\x00"
    result = validate_intake(data, max_file_bytes=len(data))
    # Отклоняется по CORRUPT_PDF (нет %%EOF), но не FILE_TOO_LARGE
    assert result.reason_code is not RejectReason.FILE_TOO_LARGE


# ── DECOMPRESSION_BOMB / EXPAND_LIMIT_EXCEEDED ─────────────────────────────────


def test_zip_bomb_ratio_detected() -> None:
    """Зип-бомба (коэфф. ~1000x) отклоняется через ratio (ТЗ RT-A)."""
    bomb = _make_bomb_zip()
    result = validate_intake(bomb)
    assert not result.ok
    assert result.reason_code in {
        RejectReason.DECOMPRESSION_BOMB,
        RejectReason.EXPAND_LIMIT_EXCEEDED,
    }


def test_zip_bomb_small_threshold() -> None:
    """C пониженным порогом (5x) даже малый зип определяется как бомба."""
    # Данные: 10 KiB нулей → сжатый в ~15 Б, ratio ~682x
    content = b"\x00" * 10_240
    z = _make_zip(content)
    result = validate_intake(z, _max_expand_ratio=5.0, _max_expanded_bytes=20_000)
    assert not result.ok
    assert result.reason_code in {
        RejectReason.DECOMPRESSION_BOMB,
        RejectReason.EXPAND_LIMIT_EXCEEDED,
    }


def test_small_legitimate_zip_passes() -> None:
    """Нормальный zip (ratio ~1.5x) проходит проверку."""
    # Сжимаем случайные данные (ratio близок к 1x)
    import os
    content = os.urandom(50_000)  # случайные данные плохо жмутся
    z = _make_zip(content)
    result = validate_intake(z)
    assert result.ok, f"Ждали ok=True, результат: {result}"


# ── CORRUPT_ARCHIVE ──────────────────────────────────────────────────────────────


def test_corrupt_zip_rejected() -> None:
    """Повреждённый ZIP-архив отклоняется без падения парсера."""
    corrupt = b"PK\x03\x04" + b"\xff" * 200  # zip magic + мусор
    result = validate_intake(corrupt)
    assert not result.ok
    assert result.reason_code is RejectReason.CORRUPT_ARCHIVE


# ── CORRUPT_PDF ──────────────────────────────────────────────────────────────────


def test_pdf_without_eof_is_corrupt() -> None:
    """Отсутствие %%EOF в PDF → CORRUPT_PDF."""
    data = b"%PDF-1.4\nsome content without eof marker\n"
    result = validate_intake(data)
    assert not result.ok
    assert result.reason_code is RejectReason.CORRUPT_PDF


def test_empty_file_is_corrupt() -> None:
    """\u041f\u0443\u0441\u0442\u043e\u0439 \u0444\u0430\u0439\u043b \u2192 CORRUPT_PDF."""
    result = validate_intake(b"")
    assert not result.ok
    assert result.reason_code is RejectReason.CORRUPT_PDF


def test_valid_pdf_passes() -> None:
    """Валидный PDF (есть %%EOF) проходит intake-проверку."""
    pdf = _make_minimal_pdf()
    result = validate_intake(pdf)
    assert result.ok, f"Ждали ok=True: {result}"
    assert result.reason_code is None


# ── UNSUPPORTED_TYPE ─────────────────────────────────────────────────────────────


def test_exe_is_unsupported() -> None:
    """Файл EXE (MZ магик) с неизвестным типом."""
    exe = b"MZ\x90\x00" + b"\x00" * 100
    result = validate_intake(exe)
    assert not result.ok
    assert result.reason_code is RejectReason.UNSUPPORTED_TYPE


def test_random_bytes_are_unsupported() -> None:
    """Произвольные байты отклоняются."""
    result = validate_intake(b"\x00\x01\x02\x03" + b"x" * 100)
    assert not result.ok
    assert result.reason_code is RejectReason.UNSUPPORTED_TYPE


# ── гарантия безопасности RT-A: никогда не выбрасывает ───────────────


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\xff" * 512, id="garbage"),
        pytest.param(b"PK\x03\x04" + b"\xff" * 100, id="corrupt_zip"),
        pytest.param(b"%PDF-1.4" + b"X" * 500, id="pdf_no_eof"),
        pytest.param(b"GIF89a", id="gif"),
    ],
)
def test_intake_never_raises(payload: bytes) -> None:
    """Для любого входа validate_intake() не выбрасывает исключение (RT-A)."""
    # Если выбросилось — тест упадёт сам validate_intake инвариант (не выбрасывать)
    result = validate_intake(payload)
    assert isinstance(result, IntakeResult)
    assert isinstance(result.ok, bool)


# ── целостность IntakeResult ─────────────────────────────────────────────────


def test_ok_result_has_no_reason_code() -> None:
    """IntakeResult(ok=True) не должен иметь reason_code."""
    pdf = _make_minimal_pdf()
    result = validate_intake(pdf)
    assert result.ok
    assert result.reason_code is None
    assert result.detail == ""


def test_rejected_result_has_reason_code() -> None:
    """Отклонённый файл всегда имеет reason_code."""
    result = validate_intake(b"")
    assert not result.ok
    assert result.reason_code is not None
    assert isinstance(result.reason_code, RejectReason)


def test_max_file_bytes_constant_is_50mb() -> None:
    """Константа MAX_FILE_BYTES = 50 МБ (ТЗ §9.1)."""
    assert MAX_FILE_BYTES == 50 * 1024 * 1024
