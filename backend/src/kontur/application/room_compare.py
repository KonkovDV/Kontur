"""Сравнение признака по номеру помещения. Пороги только из правила.

Не пишет finding_status. Не подбирает пороги по gold.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from kontur.application.extractors.number import PageToken
from kontur.domain.models import Polygon

_REQUIRED = ("room_regex", "feature_regex", "bind_radius", "pair_jaccard_min", "max_differences")


@dataclass(frozen=True, slots=True)
class RoomSpot:
    room: str
    page: int
    room_polygon: Polygon
    feature_polygon: Polygon | None


@dataclass(frozen=True, slots=True)
class RoomDiff:
    """candidate — признак есть в ПД и нет в РД. suspicion — помещение только в РД.
    match — признак совпал. abstain — пара слишком разная или номер двоится.
    """

    kind: str
    room: str
    pd: RoomSpot | None
    rd: RoomSpot | None
    rationale: str


def room_settings(rule: Mapping[str, object]) -> dict[str, object] | None:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict) or extractor.get("type") != "room_compare":
        return None
    raw = extractor.get("room_compare")
    if not isinstance(raw, dict):
        return None
    if any(key not in raw for key in _REQUIRED):
        return None
    return raw


def compare_room_tokens(
    pd_tokens: Sequence[PageToken],
    rd_tokens: Sequence[PageToken],
    settings: Mapping[str, object],
) -> tuple[RoomDiff, ...]:
    """Пара листов по Жаккару номеров. Пустой результат — листы не сопоставились."""

    room_re = re.compile(str(settings["room_regex"]))
    feature_re = re.compile(str(settings["feature_regex"]))
    radius = _as_float(settings["bind_radius"])
    jaccard_min = _as_float(settings["pair_jaccard_min"])
    max_diff = _as_int(settings["max_differences"])
    pd_pages = _pages(pd_tokens, room_re, feature_re, radius)
    rd_pages = _pages(rd_tokens, room_re, feature_re, radius)
    if not pd_pages or not rd_pages:
        return ()
    pairs = _pair(pd_pages, rd_pages, jaccard_min)
    if not pairs:
        return ()
    out: list[RoomDiff] = []
    for pd_rooms, rd_rooms in pairs:
        out.extend(_pair_diffs(pd_rooms, rd_rooms, max_diff))
    return tuple(out)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"ожидалось число, получено {value!r}")
    return float(value)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"ожидалось целое, получено {value!r}")
    return value


def _center(polygon: Polygon) -> tuple[float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _pages(
    tokens: Sequence[PageToken],
    room_re: re.Pattern[str],
    feature_re: re.Pattern[str],
    radius: float,
) -> dict[int, dict[str, RoomSpot]]:
    by_page: dict[int, list[PageToken]] = {}
    for token in tokens:
        by_page.setdefault(token.page, []).append(token)
    pages: dict[int, dict[str, RoomSpot]] = {}
    for page, items in by_page.items():
        rooms = [item for item in items if room_re.fullmatch(item.text.strip())]
        features = [item for item in items if feature_re.fullmatch(item.text.strip())]
        counts: dict[str, int] = {}
        for item in rooms:
            counts[item.text.strip()] = counts.get(item.text.strip(), 0) + 1
        if any(count > 1 for count in counts.values()):
            pages[page] = {}
            pages[page]["__duplicate__"] = RoomSpot(
                "__duplicate__", page, rooms[0].polygon_norm, None
            )
            continue
        bound: dict[str, RoomSpot] = {}
        for item in rooms:
            feature_poly = _nearest_feature(item, features, radius)
            bound[item.text.strip()] = RoomSpot(
                item.text.strip(),
                page,
                item.polygon_norm,
                feature_poly,
            )
        if bound:
            pages[page] = bound
    return pages


def _nearest_feature(
    room: PageToken,
    features: Sequence[PageToken],
    radius: float,
) -> Polygon | None:
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
    return best.polygon_norm


def _pair(
    pd_pages: Mapping[int, Mapping[str, RoomSpot]],
    rd_pages: Mapping[int, Mapping[str, RoomSpot]],
    jaccard_min: float,
) -> list[tuple[Mapping[str, RoomSpot], Mapping[str, RoomSpot]]]:
    used: set[int] = set()
    pairs: list[tuple[Mapping[str, RoomSpot], Mapping[str, RoomSpot]]] = []
    for _pd_no, pd_rooms in pd_pages.items():
        best_no: int | None = None
        best_score = jaccard_min
        pd_ids = {key for key in pd_rooms if key != "__duplicate__"}
        for rd_no, rd_rooms in rd_pages.items():
            if rd_no in used:
                continue
            rd_ids = {key for key in rd_rooms if key != "__duplicate__"}
            score = _jaccard(pd_ids, rd_ids)
            if "__duplicate__" in pd_rooms or "__duplicate__" in rd_rooms:
                score = 1.0
            if score >= best_score:
                best_score = score
                best_no = rd_no
        if best_no is None:
            continue
        used.add(best_no)
        pairs.append((pd_rooms, rd_pages[best_no]))
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
    quiet = 0
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
        else:
            quiet += 1
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
    only_pd = len(pd_ids - rd_ids)
    if len(diffs) + only_pd > max_diff:
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
