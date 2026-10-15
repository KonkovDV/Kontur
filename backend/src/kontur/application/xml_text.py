"""Текст XML: текстовые узлы, без схемы пояснительной записки.

Внешние сущности не читаются. Объявление DOCTYPE отклоняется до разбора.
Пустой документ — пустые tokens, не исключение.
"""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree  # type: ignore[import-untyped]

from kontur.application.extractors.number import PageToken
from kontur.domain.models import ExtractionEngine

_UNIT = (
    (0.05, 0.05),
    (0.45, 0.05),
    (0.45, 0.08),
    (0.05, 0.08),
)
_MAX_WORDS = 8000


class XmlReadError(ValueError):
    """Файл с расширением xml не разобран. Это не неподдерживаемый формат."""


@dataclass(frozen=True, slots=True)
class XmlText:
    tokens: tuple[PageToken, ...]


def read_xml_bytes(raw: bytes) -> XmlText:
    """Слова текстовых узлов. Схема документа не интерпретируется."""

    if not raw.strip():
        raise XmlReadError("XML: не прочитан (пусто)")
    folded = raw.lstrip().lower()
    if folded.startswith(b"<!doctype") or b"<!doctype" in folded or b"<!entity" in folded:
        raise XmlReadError("XML: не прочитан (внешние сущности не читаются)")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        remove_comments=True,
    )
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise XmlReadError("XML: не прочитан (ParseError)") from exc
    words: list[str] = []
    for chunk in root.itertext():
        words.extend(part for part in chunk.split() if part)
        if len(words) > _MAX_WORDS:
            raise XmlReadError("XML: не прочитан (слишком много текста)")
    tokens = tuple(_token(word, index) for index, word in enumerate(words))
    return XmlText(tokens=tokens)


def _token(text: str, index: int) -> PageToken:
    shift = min(index, 40) * 0.02
    polygon = tuple((x, min(0.98, y + shift)) for x, y in _UNIT)
    return PageToken(
        text=text,
        page=1,
        polygon_source=polygon,
        polygon_norm=polygon,
        engine=ExtractionEngine.VECTOR,
    )
