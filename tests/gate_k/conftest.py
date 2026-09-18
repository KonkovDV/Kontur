"""Shared fixtures for Gate K tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from kontur.application.evaluate import StagePage
from kontur.application.extractors.number import PageToken
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef

MATRIX_PATH = Path("rules")


def _fake_sha256(seed: str) -> str:
    """Deterministic 64-hex string that satisfies _identity_ok."""
    return hashlib.sha256(seed.encode()).hexdigest()


def _make_doc_ref(stage: DocStage, rule_code: str) -> DocumentRef:
    seed = f"{rule_code}/{stage.value}"
    return DocumentRef(
        file_id=f"file-{seed}",
        file_hash=_fake_sha256(seed),
        approval_status=ApprovalStatus.APPROVED,
        doc_stage=stage,
    )


def _make_token(
    value: float | str,
    *,
    page: int = 1,
    x: float = 0.1,
    y: float = 0.1,
    w: float = 0.2,
    h: float = 0.05,
) -> PageToken:
    """A minimal token whose polygon satisfies polygon_in_unit_square."""
    return PageToken(
        page=page,
        text=str(value),
        # polygon_norm: [x0,y0,x1,y1,x2,y2,x3,y3] all in [0,1]
        polygon_norm=(x, y, x + w, y, x + w, y + h, x, y + h),
        polygon_source=(x * 1000, y * 1000, (x + w) * 1000, y * 1000,
                        (x + w) * 1000, (y + h) * 1000, x * 1000, (y + h) * 1000),
    )


def _synthetic_pages(
    rule: dict[str, Any],
    *,
    pd_value: float | str,
    rd_value: float | str,
) -> dict[DocStage, StagePage]:
    """Build minimal StagePage objects that pass _identity_ok."""
    code = str(rule["code"])
    result: dict[DocStage, StagePage] = {}
    for stage, value in [(DocStage.PD, pd_value), (DocStage.RD, rd_value)]:
        doc = _make_doc_ref(stage, code)
        token = _make_token(value)
        result[stage] = StagePage(document=doc, tokens=(token,))
    return result


@pytest.fixture(scope="session")
def matrix_rules() -> list[dict[str, Any]]:
    """Load all compiled rules from rules/ directory."""
    rules: list[dict[str, Any]] = []
    if not MATRIX_PATH.exists():
        pytest.skip("rules/ directory not found — run compile_matrix.py first")
    for path in sorted(MATRIX_PATH.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            obj = json.load(f)
        # Support both single rule and list-of-rules JSON
        if isinstance(obj, list):
            rules.extend(obj)
        elif isinstance(obj, dict):
            rules.append(obj)
    if not rules:
        pytest.skip("No rules found in rules/")
    return rules


@pytest.fixture(scope="session")
def make_synthetic_pages():
    return _synthetic_pages
