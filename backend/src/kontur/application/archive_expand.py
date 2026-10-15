"""Zip с PDF, DOCX и XML. 7z и rar не распаковываются.

Бомба отклоняется по центральному каталогу, без чтения содержимого.
Путь с `..` и абсолютный путь в архив не входят.
"""

from __future__ import annotations

import io
import zipfile

from kontur.application.intake import archive_looks_like_bomb

_DOCUMENT_SUFFIXES = (".pdf", ".docx", ".xml")
_MAX_MEMBERS = 40


def expand_zip(file_id: str, payload: bytes) -> tuple[tuple[str, bytes], ...]:
    """Имена и байты документов внутри zip. Ошибка — ValueError, без подмены."""

    if archive_looks_like_bomb(payload):
        raise ValueError(f"{file_id}: ZIP: отклонён как бомба")
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{file_id}: ZIP: не прочитан") from exc
    documents: list[tuple[str, bytes]] = []
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            if _unsafe_name(name):
                raise ValueError(f"{file_id}: ZIP: небезопасное имя {name}")
            suffix = _suffix(name)
            if suffix not in _DOCUMENT_SUFFIXES:
                continue
            try:
                content = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
                raise ValueError(f"{file_id}: ZIP: не прочитан") from exc
            documents.append((name.rsplit("/", 1)[-1], content))
    if len(documents) > _MAX_MEMBERS:
        raise ValueError(f"{file_id}: ZIP: больше {_MAX_MEMBERS} документов")
    if not documents:
        raise ValueError(f"{file_id}: ZIP: нет PDF, DOCX или XML")
    return tuple(documents)


def _suffix(name: str) -> str:
    dot = name.rfind(".")
    if dot < 0:
        return ""
    return name[dot:].lower()


def _unsafe_name(name: str) -> bool:
    if not name or name.startswith("/") or name.startswith("\\"):
        return True
    return any(part in {"", ".", ".."} for part in name.split("/"))
