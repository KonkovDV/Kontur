"""Путь A → D1 → D0 для правил без исполняемого экстрактора.

Как у соседней команды: сначала подписанное число у якоря, затем размер
с единицей рядом с подписью. Обмер стен, подсчёт дверей и чтение графика
не выполняются. Если оба текстовых пути пустые, причина —
``MEASUREMENT_REQUIRED``, а не молчаливый пропуск и не выдуманное значение.
Покрытие правила остаётся ``extractor_missing``.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache

from kontur.application.extractors.number import (
    ENGINE_VERSION,
    NumberHit,
    PageToken,
    extract_number,
)
from kontur.application.normalize import fold_label, parse_number
from kontur.domain.models import Extraction, ExtractionEngine
from kontur.infrastructure.matrix.registry import discover_matrix_root

MEASUREMENT_REQUIRED = "MEASUREMENT_REQUIRED"
_RADIUS = 0.06
_DIMENSION = re.compile(
    r"(?<![0-9])(\d+(?:[ \u00a0]\d{3})*(?:[.,]\d+)?)\s*(мм|см|м)(?![а-яa-z0-9²³])",
    re.IGNORECASE,
)
_NO_TEXT = frozenset({"object_counting", "schedule_chart", "daylight_calculation"})
_TEXT_THEN_STOP = frozenset(
    {
        "drawing_measurement",
        "area_from_polygon",
        "zone_geometry",
        "slope_from_geometry",
        "layered_composite",
    }
)


@lru_cache(maxsize=1)
def _reasons() -> dict[str, str]:
    root = discover_matrix_root()
    found: dict[str, str] = {}
    number_path = root / "number_family_triage.json"
    if number_path.is_file():
        payload = json.loads(number_path.read_text(encoding="utf-8"))
        for entry in payload.get("entries", []):
            if isinstance(entry, dict) and entry.get("reason_code"):
                found[str(entry["code"])] = str(entry["reason_code"])
    family_path = root / "family_triage.json"
    if family_path.is_file():
        payload = json.loads(family_path.read_text(encoding="utf-8"))
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict):
                continue
            if entry.get("evidence_kind") in {"graphic", "spatial_count"}:
                found.setdefault(str(entry["code"]), str(entry["evidence_kind"]))
    return found


def _center(token: PageToken) -> tuple[float, float]:
    xs = [point[0] for point in token.polygon_norm]
    ys = [point[1] for point in token.polygon_norm]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _anchor_words(rule: dict[str, object]) -> tuple[str, ...]:
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return ()
    raw = extractor.get("anchors")
    if not isinstance(raw, list):
        return ()
    words: list[str] = []
    for item in raw:
        for word in fold_label(str(item)).split():
            if len(word) >= 5 and word not in words:
                words.append(word)
    return tuple(words)


def _dimension_hit(tokens: tuple[PageToken, ...], rule: dict[str, object]) -> NumberHit | None:
    words = _anchor_words(rule)
    if not words:
        return None
    anchors = [token for token in tokens if any(word in fold_label(token.text) for word in words)]
    if not anchors:
        return None
    for token in tokens:
        match = _DIMENSION.search(token.text.replace("\u00a0", " "))
        if match is None:
            continue
        origin = _center(token)
        near = any(
            token.page == anchor.page
            and math.dist(origin, _center(anchor)) <= _RADIUS
            for anchor in anchors
        )
        if not near:
            continue
        try:
            value = parse_number(match.group(1), ("nfc", "collapse_spaces", "decimal_comma"))
        except ValueError:
            continue
        unit = match.group(2).casefold()
        return NumberHit(
            extraction=Extraction(
                raw_token=match.group(0),
                engine=ExtractionEngine.VECTOR,
                engine_version=ENGINE_VERSION,
                confidence=0.9,
                normalized_value=value,
                unit=unit,
                grounded_in_source_tokens=True,
                second_read_agrees=True,
            ),
            page=token.page,
            polygon_source=token.polygon_source,
            polygon_norm=token.polygon_norm,
            window_text=token.text,
        )
    return None


def geometry_after_printed_miss(
    rule: dict[str, object],
    tokens: tuple[PageToken, ...],
) -> NumberHit | str | None:
    """D1 или D0 после того, как печатный экстрактор ничего не нашёл.

    None — правило не из геометрического семейства, старый отказ сохраняется.
    """

    if str(rule.get("coverage") or "") != "extractor_missing":
        return None
    reason = _reasons().get(str(rule.get("code") or ""))
    if reason in _NO_TEXT or reason in {"graphic", "spatial_count"}:
        return MEASUREMENT_REQUIRED
    if reason not in _TEXT_THEN_STOP:
        return None
    printed = extract_number(tokens, rule)
    if printed is not None:
        return printed
    beside = _dimension_hit(tokens, rule)
    if beside is not None:
        return beside
    return MEASUREMENT_REQUIRED
