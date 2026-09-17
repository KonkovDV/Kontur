"""Проверка целостности и безопасности входящих файлов (ТЗ §9.1).

Реализует Red Team RT-A:
  - Обнаружение архивов-бомб (анализ zip-заголовков, без распаковки данных)
  - Проверка повреждённых PDF (ТЗ §9.1 «загружен повреждённый PDF-файл»)
  - Ограничение размера файла 50 МБ (ТЗ §9.1)

Гарантия безопасности: `validate_intake()` никогда не выбрасывает
исключения вызывающему коду — все ошибки перехватываются и возвращаются
как IntakeResult(ok=False, reason_code=...). Парсер не падает.

REFERENCES
  ТЗ §9.1: лимиты 50 МБ / 200 МБ
  RT-A (docs/RED_TEAM.md): отклонение архива-бомбы с reason_code
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from enum import Enum

# ── константы (ТЗ §9.1) ──────────────────────────────────────────────────────────────

MAX_FILE_BYTES: int = 50 * 1024 * 1024      # 50 МБ на файл (ТЗ §9.1)
MAX_TOTAL_BYTES: int = 200 * 1024 * 1024    # 200 МБ суммарно (ТЗ §9.1)
_MAX_EXPAND_RATIO: float = 100.0            # x100 — порог bomb-детекции
_MAX_EXPANDED_BYTES: int = 100 * 1024 * 1024  # 100 МБ макс. uncompressed за один zip

# ПСЕВДО-опции для тестов — снижают порог до безопасных значений
_TEST_MAX_EXPAND_RATIO: float = 5.0         # только для unit-test fixture
_TEST_MAX_EXPANDED_BYTES: int = 10 * 1024   # только для unit-test fixture

# Magic bytes
_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF"


# ── публичные типы ────────────────────────────────────────────────────────────────

class RejectReason(str, Enum):
    """reason_code при отклонении файла."""

    FILE_TOO_LARGE = "FILE_TOO_LARGE"        # > 50 МБ
    DECOMPRESSION_BOMB = "DECOMPRESSION_BOMB"  # expansion ratio > 100x
    EXPAND_LIMIT_EXCEEDED = "EXPAND_LIMIT_EXCEEDED"  # uncompressed > 100 МБ
    CORRUPT_PDF = "CORRUPT_PDF"              # отсутствует %%EOF / пустой
    CORRUPT_ARCHIVE = "CORRUPT_ARCHIVE"      # повреждённый zip
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"    # неизвестный тип


@dataclass(frozen=True, slots=True)
class IntakeResult:
    """Results returned by validate_intake()."""

    ok: bool
    reason_code: RejectReason | None = None
    detail: str = ""


# ── внутренние вспомогательные функции ──────────────────────────────────────────

def _is_zip(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == _ZIP_MAGIC


def _is_pdf(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == _PDF_MAGIC


def _check_zip(
    data: bytes,
    max_expand_ratio: float,
    max_expanded_bytes: int,
) -> IntakeResult:
    """Проверить zip на bomb через анализ метаданных (без распаковки!).

    Техника: читаем только ZIP Central Directory.
    compress_size и file_size указаны в заголовке без распаковки.
    """
    try:
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            total_compressed = 0
            total_uncompressed = 0
            for info in zf.infolist():
                total_compressed += max(0, info.compress_size or 0)
                total_uncompressed += max(0, info.file_size or 0)

            # Проверка абсолютного лимита размера
            if total_uncompressed > max_expanded_bytes:
                return IntakeResult(
                    ok=False,
                    reason_code=RejectReason.EXPAND_LIMIT_EXCEEDED,
                    detail=(
                        f"Uncompressed {total_uncompressed:,} B "
                        f"> лимит {max_expanded_bytes:,} B"
                    ),
                )

            # Проверка ratio
            if total_compressed > 0:
                ratio = total_uncompressed / total_compressed
                if ratio > max_expand_ratio:
                    return IntakeResult(
                        ok=False,
                        reason_code=RejectReason.DECOMPRESSION_BOMB,
                        detail=(
                            f"Expansion ratio {ratio:.1f}x "
                            f"> порог {max_expand_ratio:.0f}x"
                        ),
                    )

    except zipfile.BadZipFile as exc:
        return IntakeResult(
            ok=False,
            reason_code=RejectReason.CORRUPT_ARCHIVE,
            detail=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        return IntakeResult(
            ok=False,
            reason_code=RejectReason.CORRUPT_ARCHIVE,
            detail=f"Unexpected: {exc}",
        )

    return IntakeResult(ok=True)


def _check_pdf(data: bytes) -> IntakeResult:
    """Минимальная проверка PDF: magic bytes + наличие %%EOF.

    Не полная валидация PDF (она выполняется парсером pdfium),
    но достаточная чтобы отклонить очевидно повреждённые файлы.
    """
    if not data:
        return IntakeResult(
            ok=False,
            reason_code=RejectReason.CORRUPT_PDF,
            detail="Пустой файл",
        )
    if not _is_pdf(data):
        return IntakeResult(
            ok=False,
            reason_code=RejectReason.UNSUPPORTED_TYPE,
            detail=f"Файл не является PDF: magic={data[:4].hex()!r}",
        )
    # Проверяем наличие %%EOF в хвосте (PDF spec. ISO 32000)
    tail = data[-2048:] if len(data) >= 2048 else data
    if b"%%EOF" not in tail and b"%%EOF" not in data[-64:]:
        # Упрощённая форма (некоторые генераторы пишут %EOF)
        if b"%EOF" not in tail:
            return IntakeResult(
                ok=False,
                reason_code=RejectReason.CORRUPT_PDF,
                detail="Отсутствует маркер %%EOF в хвосте файла",
            )
    return IntakeResult(ok=True)


# ── публичный API ────────────────────────────────────────────────────────────────

def validate_intake(
    data: bytes,
    *,
    filename: str = "",
    max_file_bytes: int = MAX_FILE_BYTES,
    _max_expand_ratio: float = _MAX_EXPAND_RATIO,
    _max_expanded_bytes: int = _MAX_EXPANDED_BYTES,
) -> IntakeResult:
    """Проверить входящий файл на безопасность и целостность (ТЗ §9.1).

    Args:
        data: Содержимое файла в памяти.
        filename: Имя файла (log-only, не влияет на логику).
        max_file_bytes: Лимит размера файла (по умолчанию 50 МБ).
        _max_expand_ratio: Внутренний параметр для unit-тестов.
        _max_expanded_bytes: Внутренний параметр для unit-тестов.

    Returns:
        IntakeResult(ok=True)  — файл принят.
        IntakeResult(ok=False, reason_code=...) — файл отклонён.

    Raises:
        Никогда. Все исключения перехватываются внутри — парсер не падает.
    """
    try:
        # Шаг 1: размер файла
        if len(data) > max_file_bytes:
            return IntakeResult(
                ok=False,
                reason_code=RejectReason.FILE_TOO_LARGE,
                detail=(
                    f"{len(data):,} Б > лимит {max_file_bytes:,} Б"
                    + (f" ('{filename}')" if filename else "")
                ),
            )

        # Шаг 2: пустой файл
        if not data:
            return IntakeResult(
                ok=False,
                reason_code=RejectReason.CORRUPT_PDF,
                detail="Пустой файл",
            )

        # Шаг 3: определить тип и вызвать соответствующую проверку
        if _is_zip(data):
            return _check_zip(data, _max_expand_ratio, _max_expanded_bytes)
        if _is_pdf(data):
            return _check_pdf(data)

        # Шаг 4: неизвестный тип
        return IntakeResult(
            ok=False,
            reason_code=RejectReason.UNSUPPORTED_TYPE,
            detail=f"Magic bytes: {data[:8].hex()!r}",
        )

    except Exception as exc:  # noqa: BLE001
        # Паранойдный перехватчик: гарантия RT-A, что парсер не падает
        return IntakeResult(
            ok=False,
            reason_code=RejectReason.CORRUPT_PDF,
            detail=f"Unexpected exception: {type(exc).__name__}: {exc}",
        )
