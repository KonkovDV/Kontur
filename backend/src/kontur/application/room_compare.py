"""Сравнение признака по номеру помещения. Пороги только из правила.

Все пары листов с Жаккаром не ниже порога правила. Конфликт вердикта
по одному номеру — abstain этого номера. Латинские омоглифы метки
сворачиваются до регэкспа правила. Пороги из JSON не подбираются по gold.
Не пишет finding_status.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from kontur.application.extractors.number import PageToken
from kontur.domain.models import ExtractionEngine, Polygon

_REQUIRED = ("room_regex", "feature_regex", "bind_radius", "pair_jaccard_min", "max_differences")

# Латиница, которую на листе путают с кириллической меткой: B4 не становится правилом,
# но одиночная «B» читается как «В» до уже заданного feature_regex.
_LATIN_LOOKALIKES = str.maketrans(
    {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "a": "а",
        "c": "с",
        "e": "е",
        "o": "о",
        "p": "р",
        "x": "х",
    }
)


@dataclass(frozen=True, slots=True)
class RoomSpot:
    room: str
    page: int
    room_polygon_source: Polygon
    room_polygon: Polygon
    feature_polygon_source: Polygon | None
    feature_polygon: Polygon | None
    engine: ExtractionEngine
    feature_engine: ExtractionEngine | None = None


@dataclass(frozen=True, slots=True)
class RoomDiff:
    """candidate — признак есть в ПД и нет в РД.
    suspicion — признак или номер есть только на одной стороне.
    abstain — номер двоится на листе или различий больше порога правила.
    """

    kind: str
    room: str
    pd: RoomSpot | None
    rd: RoomSpot | None
    rationale: str


def room_block(rule: Mapping[str, object]) -> dict[str, object] | None:
    """Пороги room_compare без требования type. Пусто, если блок неполный."""

    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return None
    raw = extractor.get("room_compare")
    if not isinstance(raw, dict):
        return None
    if any(key not in raw for key in _REQUIRED):
        return None
    return raw


def room_settings(rule: Mapping[str, object]) -> dict[str, object] | None:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict) or extractor.get("type") != "room_compare":
        return None
    return room_block(rule)


def label_text(text: str) -> str:
    """NFC и латинские омоглифы метки. Порог и регэксп правила не меняет."""

    return unicodedata.normalize("NFC", text).translate(_LATIN_LOOKALIKES).strip()


def compare_room_tokens(
    pd_tokens: Sequence[PageToken],
    rd_tokens: Sequence[PageToken],
    settings: Mapping[str, object],
) -> tuple[RoomDiff, ...]:
    """Все пары листов с Жаккаром не ниже порога.

    Пустой результат — ни одна пара не сопоставилась.
    """

    room_re = re.compile(str(settings["room_regex"]))
    feature_re = re.compile(str(settings["feature_regex"]))
    radius = _as_float(settings["bind_radius"])
    jaccard_min = _as_float(settings["pair_jaccard_min"])
    max_diff = _as_int(settings["max_differences"])
    pd_pages = _pages(pd_tokens, room_re, feature_re, radius)
    rd_pages = _pages(rd_tokens, room_re, feature_re, radius)
    abstains, pd_clean = _without_duplicates(pd_pages)
    rd_abstains, rd_clean = _without_duplicates(rd_pages)
    out = list(abstains)
    out.extend(rd_abstains)
    if pd_clean and rd_clean:
        for pd_rooms, rd_rooms in _pair(pd_clean, rd_clean, jaccard_min):
            out.extend(_pair_diffs(pd_rooms, rd_rooms, max_diff))
    return collapse_room_diffs(out)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"ожидалось число, получено {value!r}")
    return float(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"ожидалось целое, получено {value!r}")
    return value


def collapse_room_diffs(diffs: Sequence[RoomDiff]) -> tuple[RoomDiff, ...]:
    """Один номер — один вердикт. Разные двусторонние виды гасят номер.

    Пометка «номер только на одном листе» не отменяет пару, где номер есть
    на обоих листах: это соседний лист, а не второй вердикт.
    """

    sheet: list[RoomDiff] = []
    by_room: dict[str, list[RoomDiff]] = {}
    for item in diffs:
        if not item.room:
            sheet.append(item)
            continue
        by_room.setdefault(item.room, []).append(item)
    out = list(sheet)
    for room in sorted(by_room):
        group = by_room[room]
        sided = [item for item in group if item.pd is not None and item.rd is not None]
        use = sided or [item for item in group if item.pd is None or item.rd is None]
        kinds = {item.kind for item in use}
        positives = kinds & {"candidate", "suspicion"}
        if len(positives) > 1 or (positives and "match" in kinds):
            out.append(
                RoomDiff(
                    "abstain",
                    room,
                    None,
                    None,
                    f"помещение {room}: конфликт пар листов",
                )
            )
            continue
        if positives:
            chosen = [item for item in use if item.kind in positives]
            out.append(min(chosen, key=_diff_order))
            continue
        matches = [item for item in use if item.kind == "match"]
        if matches:
            out.append(min(matches, key=_diff_order))
    return tuple(out)


def _diff_order(item: RoomDiff) -> tuple[int, int]:
    pd_page = 0 if item.pd is None else item.pd.page
    rd_page = 0 if item.rd is None else item.rd.page
    return (pd_page, rd_page)


def _center(polygon: Polygon) -> tuple[float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _inner(pattern: re.Pattern[str]) -> str:
    body = pattern.pattern
    if body.startswith("^"):
        body = body[1:]
    if body.endswith("$"):
        body = body[:-1]
    return body


def _pieces(text: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    """Целый номер или склейка номеров без мусора. «500×300» не режется."""

    stripped = text.strip()
    if pattern.fullmatch(stripped):
        return (stripped,)
    body = _inner(pattern)
    part = re.compile(body)

    def walk(rest: str) -> tuple[str, ...] | None:
        if not rest:
            return ()
        for end in range(1, len(rest) + 1):
            piece = rest[:end]
            if part.fullmatch(piece) is None:
                continue
            tail = walk(rest[end:])
            if tail is not None:
                return (piece, *tail)
        return None

    parts = walk(stripped)
    if parts is None or len(parts) < 2:
        return ()
    return parts


def _expand(
    tokens: Sequence[PageToken],
    room_re: re.Pattern[str],
    feature_re: re.Pattern[str],
) -> list[PageToken]:
    expanded: list[PageToken] = []
    for token in tokens:
        parts = _pieces(token.text, room_re) or _pieces(token.text, feature_re)
        expanded.extend(replace(token, text=part) for part in parts)
    return expanded


def _without_duplicates(
    pages: Mapping[int, Mapping[str, RoomSpot]],
) -> tuple[tuple[RoomDiff, ...], dict[int, Mapping[str, RoomSpot]]]:
    abstains: list[RoomDiff] = []
    clean: dict[int, Mapping[str, RoomSpot]] = {}
    for number, rooms in pages.items():
        if "__duplicate__" in rooms:
            abstains.append(
                RoomDiff("abstain", "", None, None, "номер помещения повторяется на листе")
            )
            continue
        clean[number] = rooms
    return tuple(abstains), clean


def _pages(
    tokens: Sequence[PageToken],
    room_re: re.Pattern[str],
    feature_re: re.Pattern[str],
    radius: float,
) -> dict[int, dict[str, RoomSpot]]:
    by_page: dict[int, list[PageToken]] = {}
    for token in tokens:
        text = label_text(token.text)
        if not text:
            continue
        by_page.setdefault(token.page, []).append(replace(token, text=text))
    pages: dict[int, dict[str, RoomSpot]] = {}
    for page, items in by_page.items():
        expanded = _expand(items, room_re, feature_re)
        rooms = [item for item in expanded if room_re.fullmatch(item.text.strip())]
        features = [item for item in expanded if feature_re.fullmatch(item.text.strip())]
        counts: dict[str, int] = {}
        for item in rooms:
            counts[item.text.strip()] = counts.get(item.text.strip(), 0) + 1
        if any(count > 1 for count in counts.values()):
            pages[page] = {
                "__duplicate__": RoomSpot(
                    "__duplicate__",
                    page,
                    rooms[0].polygon_source,
                    rooms[0].polygon_norm,
                    None,
                    None,
                    rooms[0].engine,
                )
            }
            continue
        bound: dict[str, RoomSpot] = {}
        for item in rooms:
            feature = _nearest_feature(item, features, radius)
            feature_source = None if feature is None else feature.polygon_source
            feature_norm = None if feature is None else feature.polygon_norm
            feature_engine = None if feature is None else feature.engine
            bound[item.text.strip()] = RoomSpot(
                item.text.strip(),
                page,
                item.polygon_source,
                item.polygon_norm,
                feature_source,
                feature_norm,
                item.engine,
                feature_engine,
            )
        if bound:
            pages[page] = bound
    return pages


def _nearest_feature(
    room: PageToken,
    features: Sequence[PageToken],
    radius: float,
) -> PageToken | None:
    origin = _center(room.polygon_norm)
    best: PageToken | None = None
    best_dist = radius
    ambiguous = False
    for feature in features:
        if feature.page != room.page:
            continue
        dist = math.hypot(
            *[a - b for a, b in zip(origin, _center(feature.polygon_norm), strict=True)]
        )
        if dist < best_dist - 1e-9:
            best = feature
            best_dist = dist
            ambiguous = False
        elif abs(dist - best_dist) <= 1e-9:
            ambiguous = True
    if best is None or ambiguous:
        return None
    return best


def _pair(
    pd_pages: Mapping[int, Mapping[str, RoomSpot]],
    rd_pages: Mapping[int, Mapping[str, RoomSpot]],
    jaccard_min: float,
) -> list[tuple[Mapping[str, RoomSpot], Mapping[str, RoomSpot]]]:
    """Каждая пара листов не ниже порога. Лист РД не выбывает после первой пары."""

    pairs: list[tuple[Mapping[str, RoomSpot], Mapping[str, RoomSpot]]] = []
    for pd_no in sorted(pd_pages):
        pd_rooms = pd_pages[pd_no]
        pd_ids = {key for key in pd_rooms if key != "__duplicate__"}
        for rd_no in sorted(rd_pages):
            rd_rooms = rd_pages[rd_no]
            rd_ids = {key for key in rd_rooms if key != "__duplicate__"}
            if _jaccard(pd_ids, rd_ids) >= jaccard_min:
                pairs.append((pd_rooms, rd_rooms))
    return pairs


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _pair_diffs(
    pd_rooms: Mapping[str, RoomSpot],
    rd_rooms: Mapping[str, RoomSpot],
    max_diff: int,
) -> tuple[RoomDiff, ...]:
    if "__duplicate__" in pd_rooms or "__duplicate__" in rd_rooms:
        return (
            RoomDiff(
                "abstain",
                "",
                None,
                None,
                "номер помещения повторяется на листе",
            ),
        )
    pd_ids = set(pd_rooms)
    rd_ids = set(rd_rooms)
    diffs: list[RoomDiff] = []
    for room in sorted(pd_ids & rd_ids):
        pd_spot = pd_rooms[room]
        rd_spot = rd_rooms[room]
        if pd_spot.feature_polygon is not None and rd_spot.feature_polygon is None:
            diffs.append(
                RoomDiff(
                    "candidate",
                    room,
                    pd_spot,
                    rd_spot,
                    f"помещение {room}: признак есть в ПД и нет в РД",
                )
            )
        elif rd_spot.feature_polygon is not None and pd_spot.feature_polygon is None:
            diffs.append(
                RoomDiff(
                    "suspicion",
                    room,
                    pd_spot,
                    rd_spot,
                    f"помещение {room}: признак есть в РД и нет в ПД",
                )
            )
    for room in sorted(rd_ids - pd_ids):
        diffs.append(
            RoomDiff(
                "suspicion",
                room,
                None,
                rd_rooms[room],
                f"помещение {room}: есть в РД и нет в ПД",
            )
        )
    for room in sorted(pd_ids - rd_ids):
        diffs.append(
            RoomDiff(
                "suspicion",
                room,
                pd_rooms[room],
                None,
                f"помещение {room}: есть в ПД и нет в РД",
            )
        )
    if len(diffs) > max_diff:
        return (
            RoomDiff(
                "abstain",
                "",
                None,
                None,
                "на паре листов различий больше порога правила",
            ),
        )
    if diffs:
        return tuple(diffs)
    sample = next(iter(pd_rooms.values()))
    other = rd_rooms.get(sample.room)
    return (
        RoomDiff(
            "match",
            sample.room,
            sample,
            other,
            f"помещение {sample.room}: признак на паре листов совпал",
        ),
    )
