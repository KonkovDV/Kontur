"""Фраза проекта «пом. N предусмотрен элемент» и тишина рабочей стадии.

Это гипотеза свободного поиска, не параметр матрицы. Неопределённая форма
«предусмотреть» — задание на проектирование, её не берём. Слова элемента
ищем на листе помещения, не во всём томе: чужой лист про отопление комнату
не оправдывает. Условный знак без слов в рабочей документации правило не
видит: статус остаётся подозрением.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
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
_ROOM_NUMBER = re.compile(rf"(?<!\d)({_ROOM})(?!\d)")
_AFTER_ELEMENT = re.compile(r"\bсовмещ", re.IGNORECASE)
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

    if not pd_tokens or not rd_tokens:
        return ()
    rd_ordered = _text(rd_tokens)[1]
    folded = _folded_pages(rd_ordered)
    by_page: dict[int, list[PageToken]] = {}
    for token in pd_tokens:
        by_page.setdefault(token.page, []).append(token)
    hits: list[ProvisionHit] = []
    seen: set[str] = set()
    for page in sorted(by_page):
        pd_text, pd_ordered = _text(by_page[page])
        for match in _CLAUSE.finditer(pd_text):
            element = _focus_element(match.group("element"))
            stems = _stems(element)
            if not stems:
                continue
            quote = match.group(0).strip()
            rooms = list(_split_rooms(match.group("rooms")))
            if rooms:
                anchor = _room_token(pd_ordered, rooms[0])
                if anchor is not None:
                    for extra in _wrapped_rooms(anchor, pd_ordered):
                        if extra not in rooms:
                            rooms.append(extra)
            for room in rooms:
                if room in seen:
                    continue
                pd_token = _room_token(pd_ordered, room)
                rd_token = _sheet_without_stems(rd_ordered, room, stems, folded)
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


def _focus_element(element: str) -> str:
    """«совмещенная с радиаторным отоплением» — уже другая система, не этот элемент."""

    return _AFTER_ELEMENT.split(element, maxsplit=1)[0].strip()


def _folded_pages(tokens: Sequence[PageToken]) -> dict[int, str]:
    parts: dict[int, list[str]] = {}
    for token in tokens:
        parts.setdefault(token.page, []).append(token.text)
    return {
        page: " ".join(items).casefold().replace("ё", "е")
        for page, items in parts.items()
    }


def _center(token: PageToken) -> tuple[float, float]:
    xs = [point[0] for point in token.polygon_norm]
    ys = [point[1] for point in token.polygon_norm]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _wrapped_rooms(origin: PageToken, tokens: Sequence[PageToken]) -> tuple[str, ...]:
    """Номера со следующей строки, если список оборвался запятой в конце строки."""

    if not origin.text.rstrip().endswith(","):
        return ()
    _, origin_y = _center(origin)
    band: list[PageToken] = []
    for token in tokens:
        if token.page != origin.page:
            continue
        _, token_y = _center(token)
        if not 0.004 < token_y - origin_y <= 0.045:
            continue
        if _ROOM_NUMBER.match(token.text.lstrip()):
            band.append(token)
    if not band:
        return ()
    head = min(band, key=lambda item: _center(item)[0])
    return tuple(_ROOM_NUMBER.findall(head.text))


def _sheet_without_stems(
    tokens: Sequence[PageToken],
    room: str,
    stems: Sequence[str],
    folded: Mapping[int, str],
) -> PageToken | None:
    """Лист, где номер есть, а слов элемента нет. Чужой лист комнату не оправдывает."""

    exact: list[PageToken] = []
    embedded: list[PageToken] = []
    for token in tokens:
        if token.text.strip(" ,;()") == room:
            exact.append(token)
        elif room in _ROOM_NUMBER.findall(token.text):
            embedded.append(token)
    for token in exact or embedded:
        sheet = folded.get(token.page, "")
        if not any(stem in sheet for stem in stems):
            return token
    return None


def _room_token(tokens: Sequence[PageToken], room: str) -> PageToken | None:
    """Отдельный номер или кусок «(пом. 267, 270,»."""

    embedded: PageToken | None = None
    for token in tokens:
        if token.text.strip(" ,;()") == room:
            return token
        if embedded is None and room in _ROOM_NUMBER.findall(token.text):
            embedded = token
    return embedded
