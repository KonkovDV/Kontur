"""Приём файлов: лимиты, форматы и коды отказа (ТЗ п. 9.1, п. 12).

Модуль намеренно не знает про FastAPI: решение о приёме — чистая функция,
которую можно проверить тестом и переиспользовать и в HTTP-ручке, и в
консольной загрузке, и в шлюзе. Раньше лимиты существовали только как
константы в обработчике, поэтому «50 МБ» и «200 МБ» нигде не проверялись.

Границы намеренно двоичные: 50 × 1024 × 1024 больше, чем 50 000 000, поэтому
такой порог не отклонит файл, который организатор считает допустимым. Если в
приёмке имеются в виду десятичные мегабайты, меняется одна константа.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

#: ТЗ п. 9.1: один файл — не больше 50 МБ.
MAX_FILE_BYTES: int = 50 * 1024 * 1024

#: ТЗ п. 9.1: пакет — не больше 200 МБ.
MAX_BATCH_BYTES: int = 200 * 1024 * 1024

#: Псевдоимя для отказа, относящегося к пакету целиком, а не к файлу.
BATCH_SCOPE: str = "*"

#: Перечень форматов п. 9.1: PDF, DOCX, XML. DWG остаётся NOT_SUPPORTED до
#: ответа на вопрос 6 (п. 11 требует CV-анализ DWG, а перечень его не содержит).
ALLOWED_DOCUMENT_SUFFIXES: frozenset[str] = frozenset({".pdf", ".docx", ".xml"})
ALLOWED_ARCHIVE_SUFFIXES: frozenset[str] = frozenset({".zip", ".7z", ".rar"})
ALLOWED_SUFFIXES: frozenset[str] = ALLOWED_DOCUMENT_SUFFIXES | ALLOWED_ARCHIVE_SUFFIXES

#: Сигнатуры: расширение без содержимого ничего не гарантирует. DOCX — это ZIP,
#: поэтому у них общая сигнатура; различает их дальнейший разбор, не приём.
MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".docx": (b"PK\x03\x04",),
    ".xml": (b"<", b"\xef\xbb\xbf<"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".7z": (b"7z\xbc\xaf\x27\x1c",),
    ".rar": (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
}

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SEPARATORS = re.compile(r"[\\/]")
_MAX_NAME_BYTES = 255


class RejectionReason(StrEnum):
    """Коды отказа приёма.

    Первые семь — дословный перечень ТЗ п. 9.1 и enum `RejectionReason`
    контракта. `UNSAFE_FILENAME` — расширение по п. 12: имя с разделителями
    путей или управляющими символами нельзя принимать в объектное хранилище.
    """

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    BATCH_LIMIT_EXCEEDED = "BATCH_LIMIT_EXCEEDED"
    ANTIVIRUS_REJECTED = "ANTIVIRUS_REJECTED"
    ENCRYPTED_FILE = "ENCRYPTED_FILE"
    PROCESSING_TIMEOUT = "PROCESSING_TIMEOUT"
    UNSAFE_FILENAME = "UNSAFE_FILENAME"


#: Дословный перечень ТЗ п. 9.1 — источник истины и для `pipeline`, и для OpenAPI.
TZ_REJECTION_CODES: frozenset[str] = frozenset(
    {
        RejectionReason.UNSUPPORTED_FORMAT.value,
        RejectionReason.CORRUPTED_FILE.value,
        RejectionReason.FILE_TOO_LARGE.value,
        RejectionReason.BATCH_LIMIT_EXCEEDED.value,
        RejectionReason.ANTIVIRUS_REJECTED.value,
        RejectionReason.ENCRYPTED_FILE.value,
        RejectionReason.PROCESSING_TIMEOUT.value,
    }
)

#: Расширения сверх ТЗ. Перечень обязан быть явным, иначе контракт «уползёт».
EXTRA_REJECTION_CODES: frozenset[str] = frozenset({RejectionReason.UNSAFE_FILENAME.value})

#: HTTP-коды ответа. 413 для лимитов — то, что уже обещано в OpenAPI.
HTTP_STATUS: dict[RejectionReason, int] = {
    RejectionReason.UNSUPPORTED_FORMAT: 415,
    RejectionReason.CORRUPTED_FILE: 422,
    RejectionReason.FILE_TOO_LARGE: 413,
    RejectionReason.BATCH_LIMIT_EXCEEDED: 413,
    RejectionReason.ANTIVIRUS_REJECTED: 422,
    RejectionReason.ENCRYPTED_FILE: 422,
    RejectionReason.PROCESSING_TIMEOUT: 504,
    RejectionReason.UNSAFE_FILENAME: 422,
}


@dataclass(frozen=True, slots=True)
class UploadCandidate:
    """Файл на входе. `header` — первые байты, если вызывающий уже их прочитал."""

    filename: str
    size_bytes: int
    header: bytes | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise ValueError("размер файла не может быть отрицательным")


@dataclass(frozen=True, slots=True)
class Rejection:
    filename: str
    reason: RejectionReason
    detail: str

    @property
    def http_status(self) -> int:
        return HTTP_STATUS[self.reason]


@dataclass(frozen=True, slots=True)
class IntakeDecision:
    accepted: tuple[UploadCandidate, ...]
    rejected: tuple[Rejection, ...]
    duplicates: tuple[UploadCandidate, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.rejected

    @property
    def http_status(self) -> int:
        """Худший из отказов. Пустой пакет — тоже отказ, но его решает сценарий."""

        if not self.rejected:
            return 202
        return max(item.http_status for item in self.rejected)


def suffix_of(filename: str) -> str:
    return PurePosixPath(filename).suffix.lower()


def filename_is_safe(filename: str) -> bool:
    """Имя без разделителей путей, без `..`, без управляющих символов и в 255 байт."""

    if not filename or filename != filename.strip():
        return False
    if _CONTROL_CHARS.search(filename) or _SEPARATORS.search(filename):
        return False
    if filename in {".", ".."} or filename.startswith(".."):
        return False
    return len(filename.encode("utf-8")) <= _MAX_NAME_BYTES


def header_matches_suffix(suffix: str, header: bytes | None) -> bool:
    """Содержимое не противоречит расширению. Неизвестный заголовок не обвиняем."""

    if header is None:
        return True
    prefixes = MAGIC_PREFIXES.get(suffix)
    if not prefixes:
        return True
    return any(header.startswith(prefix) for prefix in prefixes)


def check_file(candidate: UploadCandidate) -> Rejection | None:
    """Проверки одного файла в порядке дешевизны: имя, формат, размер, сигнатура."""

    name = candidate.filename
    if not filename_is_safe(name):
        return Rejection(
            filename=name,
            reason=RejectionReason.UNSAFE_FILENAME,
            detail="имя файла содержит разделитель пути, `..` или управляющий символ",
        )
    suffix = suffix_of(name)
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        return Rejection(
            filename=name,
            reason=RejectionReason.UNSUPPORTED_FORMAT,
            detail=f"расширение {suffix or '<нет>'} не поддерживается; допустимо: {allowed}",
        )
    if candidate.size_bytes == 0:
        return Rejection(
            filename=name,
            reason=RejectionReason.CORRUPTED_FILE,
            detail="файл нулевой длины",
        )
    if candidate.size_bytes > MAX_FILE_BYTES:
        return Rejection(
            filename=name,
            reason=RejectionReason.FILE_TOO_LARGE,
            detail=f"{candidate.size_bytes} Б больше лимита {MAX_FILE_BYTES} Б (50 МБ)",
        )
    if not header_matches_suffix(suffix, candidate.header):
        return Rejection(
            filename=name,
            reason=RejectionReason.CORRUPTED_FILE,
            detail=f"содержимое не похоже на {suffix}: сигнатура не совпала",
        )
    return None


def evaluate_batch(candidates: Iterable[UploadCandidate]) -> IntakeDecision:
    """Решение по пакету.

    Лимит пакета считается по всем присланным байтам, а не только по принятым:
    200 МБ — это граница того, что вообще разрешено загрузить за один запрос.
    Дубликаты по `content_hash` не отказ, а нормальная дедупликация (в БД тот
    же инвариант держит `UNIQUE (object_id, file_hash, doc_stage)`).
    """

    items = list(candidates)
    rejected: list[Rejection] = []
    accepted: list[UploadCandidate] = []
    duplicates: list[UploadCandidate] = []
    seen_hashes: set[str] = set()

    total = sum(item.size_bytes for item in items)
    if total > MAX_BATCH_BYTES:
        rejected.append(
            Rejection(
                filename=BATCH_SCOPE,
                reason=RejectionReason.BATCH_LIMIT_EXCEEDED,
                detail=f"{total} Б больше лимита {MAX_BATCH_BYTES} Б (200 МБ)",
            )
        )
        return IntakeDecision(accepted=(), rejected=tuple(rejected))

    for item in items:
        problem = check_file(item)
        if problem is not None:
            rejected.append(problem)
            continue
        if item.content_hash is not None:
            if item.content_hash in seen_hashes:
                duplicates.append(item)
                continue
            seen_hashes.add(item.content_hash)
        accepted.append(item)

    return IntakeDecision(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        duplicates=tuple(duplicates),
    )
