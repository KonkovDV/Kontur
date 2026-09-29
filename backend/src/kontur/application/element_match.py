"""Совпадение марки установки на двух листах.

Это сигнал инспектору, не вердикт матрицы. Статус всегда SUSPICION.
Попаданием в скоринге считается только CANDIDATE.
Порог перекрытия задан заранее и не подбирается по шести золотым строкам.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from kontur.application.extractors.number import PageToken
from kontur.application.suspicion import SuspicionApproach, SuspicionSignal
from kontur.domain.geometry import bbox_from_polygon
from kontur.domain.models import Polygon

IOU_SAME_PLACE = 0.50
_LABEL = re.compile(r"^[ПВ]\d{1,2}$")


def _label(text: str) -> str | None:
    compact = text.replace(" ", "").replace("-", "").replace("–", "").upper()
    if _LABEL.fullmatch(compact):
        return compact
    return None


def _iou(left: Polygon, right: Polygon) -> float:
    ax0, ay0, ax1, ay1 = bbox_from_polygon(left)
    bx0, by0, bx1, by1 = bbox_from_polygon(right)
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter_w, inter_h = ix1 - ix0, iy1 - iy0
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _index(tokens: Sequence[PageToken]) -> dict[str, list[Polygon]]:
    found: dict[str, list[Polygon]] = {}
    for token in tokens:
        label = _label(token.text)
        if label is None:
            continue
        found.setdefault(label, []).append(token.polygon_norm)
    return found


def ventilation_element_suspicion(
    pd_tokens: Sequence[PageToken],
    rd_tokens: Sequence[PageToken],
    *,
    rule_code: str,
    evidence_group_id: str,
    iou_same: float = IOU_SAME_PLACE,
) -> SuspicionSignal | None:
    """Марка только с одной стороны или в другом месте листа — подозрение."""

    if not 0 < iou_same <= 1:
        raise ValueError("iou_same должен быть в (0; 1]")
    left = _index(pd_tokens)
    right = _index(rd_tokens)
    if not left and not right:
        return None
    for side in (left, right):
        repeated = [label for label, boxes in side.items() if len(boxes) > 1]
        if repeated:
            names = ", ".join(sorted(repeated))
            return SuspicionSignal(
                rule_code,
                evidence_group_id,
                SuspicionApproach.ANNOTATION_CONFLICT,
                0.70,
                detail=f"марка повторяется на одном листе: {names}",
            )
    labels = sorted(set(left) | set(right))
    matched = 0
    notes: list[str] = []
    for label in labels:
        on_left = left.get(label)
        on_right = right.get(label)
        if on_left is None or on_right is None:
            notes.append(f"{label} есть только на одной стороне")
            continue
        overlap = _iou(on_left[0], on_right[0])
        if overlap >= iou_same:
            matched += 1
            continue
        notes.append(f"{label}: перекрытие {overlap:.2f} ниже {iou_same:.2f}")
    if not notes:
        return None
    return SuspicionSignal(
        rule_code,
        evidence_group_id,
        SuspicionApproach.PARTIAL_MATCH,
        matched / len(labels),
        detail="; ".join(notes),
    )
