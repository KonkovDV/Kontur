"""Фраза проекта «пом. N предусмотрен элемент» и тишина рабочей стадии.

Это гипотеза свободного поиска, не параметр матрицы. Неопределённая форма
«предусмотреть» — задание на проектирование, её не берём. Условный знак без
слов в рабочей документации правило не видит: статус остаётся подозрением.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from kontur.application.extractors.number import PageToken
from kontur.domain.geometry import reading_key

_ROOM = r"\d{2,4}(?:\.\d)?"
_ROOMS = _ROOM + r"(?:\s*(?:,|и)\s*" + _ROOM + r")*"
_VERB = (
    r"предусмотрен[аоы]?|предусматрива(?:ет|ют)ся|"
    r"устанавлива(?:ет|ют)ся|установлен[аоы]?"
)
_CLAUSE = re.compile(
    r"(?:пом\.\s*(?:№\s*)?|помещени\w*\s*№\s*)(?P<rooms>"
    + _ROOMS
    + r")\s*\)?\s*(?P<gap>[^.;]{0,80}?)?\b(?P<verb>"
    + _VERB
    + r")\s+(?P<element>[^.;]{4,160})",
    re.IGNORECASE,
)
_PAREN = re.compile(r"\(([^)]{3,80})\)")
_WORD = re.compile(r"[а-яё]{4,}", re.IGNORECASE)
_STOP = frozenset(
    {
        "система",
        "системы",
        "систем",
        "помещение",
        "помещения",
        "помещений",
        "также",
        "этого",
        "этом",
    }
)


@dataclass(frozen=True, slots=True)
class ProvisionHit:
    room: str
    element: str
    quote: str
    pd: PageToken
    rd: PageToken


def provision_hits(
    pd_tokens: Sequence[PageToken],
    rd_tokens: Sequence[PageToken],
) -> tuple[ProvisionHit, ...]:
    """Помещение названо в обеих стадиях, элемент из фразы ПД в РД не найден."""

    pd_text, pd_ordered = _text(pd_tokens)
    rd_text, rd_ordered = _text(rd_tokens)
    if not pd_text or not rd_text:
        return ()
    rd_folded = rd_text.casefold()
    hits: list[ProvisionHit] = []
    seen: set[str] = set()
    for match in _CLAUSE.finditer(pd_text):
        element = match.group("element").strip()
        stems = _stems(element)
        if not stems:
            continue
        if any(stem.casefold() in rd_folded for stem in stems):
            continue
        quote = match.group(0).strip()
        for room in _split_rooms(match.group("rooms")):
            if room in seen:
                continue
            pd_token = _room_token(pd_ordered, room)
            rd_token = _room_token(rd_ordered, room)
            if pd_token is None or rd_token is None:
                continue
            seen.add(room)
            hits.append(
                ProvisionHit(
                    room=room,
                    element=element,
                    quote=quote[:180],
                    pd=pd_token,
                    rd=rd_token,
                )
            )
    return tuple(hits)


def _text(tokens: Sequence[PageToken]) -> tuple[str, tuple[PageToken, ...]]:
    ordered = tuple(sorted(tokens, key=lambda item: reading_key(item.page, item.polygon_norm)))
    return " ".join(item.text for item in ordered), ordered


def _split_rooms(raw: str) -> tuple[str, ...]:
    parts = re.split(r"\s*(?:,|и)\s*", raw.strip())
    return tuple(part for part in parts if part)


def _stems(element: str) -> tuple[str, ...]:
    chunks = [element, *_PAREN.findall(element)]
    stems: list[str] = []
    for chunk in chunks:
        for word in _WORD.findall(chunk):
            folded = word.casefold().replace("ё", "е")
            if folded in _STOP or folded in stems:
                continue
            stems.append(folded)
    return tuple(stems)


def _room_token(tokens: Sequence[PageToken], room: str) -> PageToken | None:
    for token in tokens:
        if token.text.strip(" ,;()") == room:
            return token
    return None
