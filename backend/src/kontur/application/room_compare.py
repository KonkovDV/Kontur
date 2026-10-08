"""Сравнение признака по номеру помещения. Пороги только из правила.

Все пары листов с Жаккаром не ниже порога правила. Номер, который так и не
попал ни в одну такую пару, сравнивается отдельно: порог при этом не
опускается. Конфликт вердикта по одному номеру — abstain этого номера.
Столбец экспликации не считается вторым экземпляром номера. Латинские
омоглифы метки сворачиваются до регэкспа правила. Пороги из JSON не
подбираются по gold. Не пишет finding_status.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from kontur.application.extractors.number import PageToken
from kontur.domain.geometry import (
    bbox_from_polygon,
    reading_key,
    union_rect_polygon,
    y_overlap,
)
from kontur.domain.models import ExtractionEngine, Polygon

_REQUIRED = ("room_regex", "feature_regex", "bind_radius", "pair_jaccard_min", "max_differences")
_MAX_JOIN = 4
_TOUCH_GAP = 0.015

# Латиница, которую на листе путают с кириллической меткой.
# B читается как В, E как Е, P как П: так пишутся марки ВЕ и П, не порог gold.
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
        "P": "П",
        "T": "Т",
        "X": "Х",
        "a": "а",
        "c": "с",
        "e": "е",
        "o": "о",
        "p": "п",
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
    boxes = _exclude_boxes(settings)
    pd_pages, pd_dups = _pages(pd_tokens, room_re, feature_re, radius, boxes)
    rd_pages, rd_dups = _pages(rd_tokens, room_re, feature_re, radius, boxes)
    out = list(pd_dups)
    out.extend(rd_dups)
    blocked: set[str] = set()
    if pd_pages and rd_pages:
        for pd_rooms, rd_rooms in _pair(pd_pages, rd_pages, jaccard_min):
            diffs = _pair_diffs(pd_rooms, rd_rooms, max_diff)
            out.extend(diffs)
            if any(item.kind == "abstain" and not item.room for item in diffs):
                blocked.update(set(pd_rooms) & set(rd_rooms))
    collapsed = list(collapse_room_diffs(out))
    settled = {item.room for item in collapsed if item.room} | blocked
    collapsed.extend(_across_sheets(pd_pages, rd_pages, settled))
    return collapse_room_diffs(collapsed)


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
        if any(item.kind == "abstain" for item in group):
            out.append(
                RoomDiff(
                    "abstain",
                    room,
                    None,
                    None,
                    f"помещение {room}: номер повторяется на листе",
                )
            )
            continue
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


def _exclude_boxes(
    settings: Mapping[str, object],
) -> tuple[tuple[float, float, float, float], ...]:
    """Прямоугольники из правила. Нет поля — ничего не вырезается."""

    raw = settings.get("exclude_bboxes")
    if not isinstance(raw, list):
        return ()
    boxes: list[tuple[float, float, float, float]] = []
    for item in raw:
        if not isinstance(item, list | tuple) or len(item) != 4:
            continue
        try:
            box = tuple(float(value) for value in item)
        except (TypeError, ValueError):
            continue
        boxes.append((box[0], box[1], box[2], box[3]))
    return tuple(boxes)


def _inside_box(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _label_match(text: str, room_re: re.Pattern[str], feature_re: re.Pattern[str]) -> bool:
    stripped = text.strip()
    return (
        room_re.fullmatch(stripped) is not None or feature_re.fullmatch(stripped) is not None
    )


def _touching(left: PageToken, right: PageToken) -> bool:
    """Соседние куски одной строки. Порог зазора не из gold и не из правила."""

    if left.page != right.page or not y_overlap(left.polygon_norm, right.polygon_norm):
        return False
    left_box = bbox_from_polygon(left.polygon_norm)
    right_box = bbox_from_polygon(right.polygon_norm)
    if left_box[0] <= right_box[0]:
        gap = right_box[0] - left_box[2]
    else:
        gap = left_box[0] - right_box[2]
    return -0.005 <= gap <= _TOUCH_GAP


def _joined(parts: Sequence[PageToken], text: str) -> PageToken:
    engines = {item.engine for item in parts}
    engine = engines.pop() if len(engines) == 1 else ExtractionEngine.VECTOR
    return replace(
        parts[0],
        text=text,
        engine=engine,
        polygon_source=union_rect_polygon(tuple(item.polygon_source for item in parts)),
        polygon_norm=union_rect_polygon(tuple(item.polygon_norm for item in parts)),
    )


def _join_touching(
    tokens: Sequence[PageToken],
    room_re: re.Pattern[str],
    feature_re: re.Pattern[str],
) -> list[PageToken]:
    """Склеить куски, которые вместе совпадают с регэкспом правила.

    «14»+«0» читается как номер, «В»+«2» как метка, «тёплый»+«пол» как признак.
    Более длинное совпадение той же строки побеждает короткое. Чужой токен не глотается.
    """

    ordered = sorted(tokens, key=lambda item: reading_key(item.page, item.polygon_norm))
    joined: list[PageToken] = []
    index = 0
    while index < len(ordered):
        run = [ordered[index]]
        best_end = index
        best_text = ordered[index].text
        cursor = index
        while cursor + 1 < len(ordered) and len(run) < _MAX_JOIN:
            nxt = ordered[cursor + 1]
            if not _touching(run[-1], nxt):
                break
            run.append(nxt)
            cursor += 1
            texts = [item.text for item in run]
            for candidate in ("".join(texts), " ".join(texts)):
                if _label_match(candidate, room_re, feature_re):
                    best_end = cursor
                    best_text = candidate
        if best_end > index:
            joined.append(_joined(ordered[index : best_end + 1], best_text))
            index = best_end + 1
            continue
        joined.append(ordered[index])
        index += 1
    return joined


def _split_room_lists(
    tokens: Sequence[PageToken],
    room_re: re.Pattern[str],
) -> list[PageToken]:
    """«267, 270» — два номера одной подписи. «500×300» не режется."""

    split: list[PageToken] = []
    for token in tokens:
        parts = [part.strip() for part in re.split(r"[,;]", token.text) if part.strip()]
        if len(parts) < 2 or any(room_re.fullmatch(part) is None for part in parts):
            split.append(token)
            continue
        split.extend(replace(token, text=part) for part in parts)
    return split


def _column_indexes(rooms: Sequence[PageToken]) -> set[int]:
    """Номера столбца. Шаг берётся с этого листа: самый плотный межстрочный зазор.

    Три таких шага ещё столбец (пропущенная строка). Два номера в разных
    местах листа столбцом не становятся.
    """

    boxes = [bbox_from_polygon(item.polygon_norm) for item in rooms]
    centers = [((box[0] + box[2]) / 2, (box[1] + box[3]) / 2) for box in boxes]
    aligned: list[tuple[int, int, float]] = []
    for index, box in enumerate(boxes):
        width = max(box[2] - box[0], 1e-6)
        height = max(box[3] - box[1], 1e-6)
        cx, cy = centers[index]
        for other_index in range(index + 1, len(boxes)):
            other = boxes[other_index]
            ox, oy = centers[other_index]
            align = max(width, other[2] - other[0], 1e-6)
            line = max(height, other[3] - other[1], 1e-6)
            dy = abs(oy - cy)
            if abs(ox - cx) <= align and dy > line:
                aligned.append((index, other_index, dy))
    if not aligned:
        return set()
    step = min(gap for _left, _right, gap in aligned)
    limit = step * 3
    neighbors: dict[int, int] = {}
    for left, right, gap in aligned:
        if gap > limit:
            continue
        neighbors[left] = neighbors.get(left, 0) + 1
        neighbors[right] = neighbors.get(right, 0) + 1
    return {index for index, hits in neighbors.items() if hits >= 2}


def _same_inscription(left: PageToken, right: PageToken) -> bool:
    """Два штриха одной подписи. Далёкие копии — разные места."""

    left_box = bbox_from_polygon(left.polygon_norm)
    right_box = bbox_from_polygon(right.polygon_norm)
    span = max(
        left_box[2] - left_box[0],
        left_box[3] - left_box[1],
        right_box[2] - right_box[0],
        right_box[3] - right_box[1],
        1e-6,
    )
    distance = math.dist(_center(left.polygon_norm), _center(right.polygon_norm))
    # Нулевая дистанция — куски одной разрезанной строки, не второй штрих.
    return 1e-9 < distance <= span * 10


def _clusters(items: Sequence[PageToken]) -> list[list[PageToken]]:
    groups: list[list[PageToken]] = []
    for item in items:
        placed = False
        for group in groups:
            if any(_same_inscription(item, other) for other in group):
                group.append(item)
                placed = True
                break
        if not placed:
            groups.append([item])
    return groups


def _choose_rooms(rooms: Sequence[PageToken]) -> tuple[list[PageToken], list[str]]:
    """Один номер на листе. Столбец экспликации не делает второй экземпляр.

    Два номера вне столбца и далеко друг от друга — abstain: это разные места.
    Повтор вплотную — одна подпись.
    """

    column = _column_indexes(rooms)
    isolated: dict[str, list[PageToken]] = {}
    stacked: dict[str, list[PageToken]] = {}
    for index, item in enumerate(rooms):
        name = item.text.strip()
        bucket = stacked if index in column else isolated
        bucket.setdefault(name, []).append(item)
    chosen: list[PageToken] = []
    repeated: list[str] = []
    for name in sorted(set(isolated) | set(stacked)):
        lone = _clusters(isolated.get(name, []))
        rows = _clusters(stacked.get(name, []))
        if len(lone) > 1 or (not lone and len(rows) > 1):
            repeated.append(name)
            continue
        chosen.append(lone[0][0] if lone else rows[0][0])
    return chosen, repeated


def _pages(
    tokens: Sequence[PageToken],
    room_re: re.Pattern[str],
    feature_re: re.Pattern[str],
    radius: float,
    boxes: Sequence[tuple[float, float, float, float]] = (),
) -> tuple[dict[int, dict[str, RoomSpot]], tuple[RoomDiff, ...]]:
    by_page: dict[int, list[PageToken]] = {}
    for token in tokens:
        text = label_text(token.text)
        if not text:
            continue
        labeled = replace(token, text=text)
        if boxes and any(_inside_box(_center(labeled.polygon_norm), box) for box in boxes):
            continue
        by_page.setdefault(token.page, []).append(labeled)
    pages: dict[int, dict[str, RoomSpot]] = {}
    abstains: list[RoomDiff] = []
    for page, items in by_page.items():
        expanded = _expand(
            _join_touching(_split_room_lists(items, room_re), room_re, feature_re),
            room_re,
            feature_re,
        )
        rooms = [item for item in expanded if room_re.fullmatch(item.text.strip())]
        features = [item for item in expanded if feature_re.fullmatch(item.text.strip())]
        chosen, repeated = _choose_rooms(rooms)
        for name in repeated:
            abstains.append(
                RoomDiff(
                    "abstain",
                    name,
                    None,
                    None,
                    f"помещение {name}: номер повторяется на листе",
                )
            )
        owned = _owned_features(chosen, features, radius)
        bound: dict[str, RoomSpot] = {}
        for item in chosen:
            name = item.text.strip()
            feature = owned.get(name)
            feature_source = None if feature is None else feature.polygon_source
            feature_norm = None if feature is None else feature.polygon_norm
            feature_engine = None if feature is None else feature.engine
            bound[name] = RoomSpot(
                name,
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
    return pages, tuple(abstains)


def _owned_features(
    rooms: Sequence[PageToken],
    features: Sequence[PageToken],
    radius: float,
) -> dict[str, PageToken]:
    """Признак достаётся ближайшему номеру.

    Ничья двух разных пузырей — никому. Ничья номеров одной подписи
    «271, 272» покрывает всю подпись.
    """

    owned: dict[str, PageToken] = {}
    for feature in features:
        origin = _center(feature.polygon_norm)
        ranked: list[tuple[float, str]] = []
        for room in rooms:
            if feature.page != room.page:
                continue
            dist = math.hypot(
                *[
                    left - right
                    for left, right in zip(origin, _center(room.polygon_norm), strict=True)
                ]
            )
            if dist <= radius + 1e-12:
                ranked.append((dist, room.text.strip()))
        ranked.sort(key=lambda item: item[0])
        if not ranked:
            continue
        if len(ranked) > 1 and ranked[1][0] <= ranked[0][0] + 1e-9:
            nearest = ranked[0][0]
            tied = [name for dist, name in ranked if dist <= nearest + 1e-9]
            if _same_list(tied, rooms):
                for name in tied:
                    owned.setdefault(name, feature)
            continue
        owned.setdefault(ranked[0][1], feature)
    return owned


def _same_list(names: Sequence[str], rooms: Sequence[PageToken]) -> bool:
    """Ничья на одной подписи «271, 272». Два разных пузыря — не список."""

    wanted = set(names)
    centers = {
        _center(item.polygon_norm)
        for item in rooms
        if item.text.strip() in wanted
    }
    return len(centers) == 1


def _prefer_marked(
    pages: Mapping[int, Mapping[str, RoomSpot]],
) -> dict[str, RoomSpot]:
    """Метка на любом листе стадии. Лист без буквы метку не отменяет."""

    chosen: dict[str, RoomSpot] = {}
    for rooms in pages.values():
        for name, spot in rooms.items():
            current = chosen.get(name)
            if current is None or (
                current.feature_polygon is None and spot.feature_polygon is not None
            ):
                chosen[name] = spot
    return chosen


def _across_sheets(
    pd_pages: Mapping[int, Mapping[str, RoomSpot]],
    rd_pages: Mapping[int, Mapping[str, RoomSpot]],
    settled: set[str],
) -> list[RoomDiff]:
    """Номер есть на обеих стадиях, но пара листов его не разобрала.

    Порог Жаккара здесь не читается и не опускается.
    """

    pd_spots = _prefer_marked(pd_pages)
    rd_spots = _prefer_marked(rd_pages)
    found: list[RoomDiff] = []
    for room in sorted(set(pd_spots) & set(rd_spots)):
        if room in settled:
            continue
        pd_spot = pd_spots[room]
        rd_spot = rd_spots[room]
        pd_mark = pd_spot.feature_polygon is not None
        rd_mark = rd_spot.feature_polygon is not None
        if pd_mark and not rd_mark:
            found.append(
                RoomDiff(
                    "candidate",
                    room,
                    pd_spot,
                    rd_spot,
                    f"помещение {room}: признак есть в ПД и нет в РД",
                )
            )
        elif rd_mark and not pd_mark:
            found.append(
                RoomDiff(
                    "suspicion",
                    room,
                    pd_spot,
                    rd_spot,
                    f"помещение {room}: признак есть в РД и нет в ПД",
                )
            )
    return found


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
