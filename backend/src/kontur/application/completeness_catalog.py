"""Таблица (1) комплектности протокола из каталога разделов ТЗ.

Строки — MISSING / STAGE_UPLOADED_NOT_VERIFIED / STAGE_PARTIAL_NOT_VERIFIED
по стадии из CompletenessMap × sections.json (не PRESENT раздела).
Это НЕ нарушения: counts_as_violation всегда false. Presence W2 / executable
матрицы не трогаем (59/132 без изменений).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness
from kontur.evaluation.agent_dumps import repo_root

_STAGE_KEY = {DocStage.PD: "pd", DocStage.RD: "rd", DocStage.ID: "id"}


@lru_cache(maxsize=1)
def load_sections_catalog(path: str | None = None) -> tuple[dict[str, object], ...]:
    """Каталог разделов data/matrix/sections.json (коды ПЗ…СМ)."""

    root = Path(path) if path else repo_root() / "data" / "matrix" / "sections.json"
    payload = json.loads(root.read_text(encoding="utf-8"))
    sections = payload.get("sections")
    if not isinstance(sections, list):
        raise ValueError("sections.json: ожидали список sections")
    out: list[dict[str, object]] = []
    for item in sections:
        if isinstance(item, dict) and item.get("code"):
            out.append(item)
    return tuple(out)


def _expected_label(section: Mapping[str, object], stage: DocStage) -> str:
    key = _STAGE_KEY[stage]
    raw = section.get(key)
    if raw is None:
        return ""
    if isinstance(raw, list):
        return ", ".join(str(x) for x in raw) if raw else ""
    return str(raw)


def completeness_rows_from_catalog(
    completeness: CompletenessMap,
    *,
    catalog: Sequence[Mapping[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Строки sections.completeness: каталог × стадия.

    MISSING стадия → outcome=MISSING (список ожидаемых документов).
    UPLOADED → STAGE_UPLOADED_NOT_VERIFIED; PARTIAL → STAGE_PARTIAL_NOT_VERIFIED.
    Не заявляем PRESENT раздела (BRIEF_PRESENCE_W2: +0 executable).
    """

    sections = catalog if catalog is not None else load_sections_catalog()
    rows: list[dict[str, object]] = []
    for section in sections:
        code = str(section.get("code") or "").strip()
        if not code:
            continue
        for stage in (DocStage.PD, DocStage.RD, DocStage.ID):
            expected = _expected_label(section, stage)
            if not expected:
                continue
            state = completeness.get(stage, Completeness.MISSING)
            # Не заявляем PRESENT раздела: presence W2 не executable.
            # Стадия загружена ≠ раздел проверен по каталогу.
            if state is Completeness.MISSING:
                outcome = "MISSING"
            elif state is Completeness.PARTIAL:
                outcome = "STAGE_PARTIAL_NOT_VERIFIED"
            else:
                outcome = "STAGE_UPLOADED_NOT_VERIFIED"
            rows.append(
                {
                    "section_code": code,
                    "stage": stage.value,
                    "expected_document": expected,
                    "upload_state": state.value,
                    "outcome": outcome,
                    "counts_as_violation": False,
                    "kind": "section_catalog",
                    # совместимость с узкими колонками экспорта (finding_id/rule_code/status)
                    "finding_id": f"completeness-{code}-{stage.value}",
                    "rule_code": f"COMPLETENESS-{code}",
                    "finding_status": outcome,  # не finding.schema; для узких колонок экспорта
                    "rationale": (
                        f"Каталог раздела {code}: ожидается «{expected}» на стадии "
                        f"{stage.value}; комплектность стадии = {state.value}. "
                        "Не нарушение."
                    ),
                }
            )
    return rows
