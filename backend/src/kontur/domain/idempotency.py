"""Стабильный ключ сравнения: одинаковый вход — одинаковый evidence_group.

Повтор доставки (at-least-once) не должен плодить новую группу доказательств
для той же тройки объект / правило / файлы-эталоны.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence


def comparison_key(object_id: str, rule_code: str, file_ids: Sequence[str]) -> str:
    """SHA-256 от канонического состава. Пустой компонент — ошибка, не тихий ключ."""

    parts = (object_id.strip(), rule_code.strip(), *(item.strip() for item in file_ids))
    if any(not item for item in parts):
        raise ValueError("ключ сравнения не собирается из пустых полей")
    blob = "\0".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
