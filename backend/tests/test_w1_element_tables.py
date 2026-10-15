"""W1: ведомости КР/ИОС3/ИОС4 через element_table (марка строки + одно число, мм).

Синтетические фикстуры — механика правила, не измеренная точность и не Gate J.
"""

from __future__ import annotations

import pytest

from kontur.application.evaluate import evaluate_rule
from kontur.domain.models import DocStage
from kontur.domain.statuses import FindingStatus

from test_contour_and_table import _completeness, _doc, _rule, _table_page

CASES = {
    "KR-059": ("КР-1", (("ПМ-1", "200"), ("ПМ-2", "220")), "180"),
    "KR-061": ("КР-1", (("Стм1", "250"), ("Стм2", "300")), "200"),
    "IOS3-074": ("ИОС3-1", (("К1-1", "110"), ("К2-1", "160")), "100"),
    "IOS4-076": ("ИОС4-1", (("Т1.1", "50"), ("Т1.2", "40")), "32"),
}


def _eval(code: str, pd_rows, rd_rows):
    doc_code = CASES[code][0]
    pd = _doc(DocStage.PD, doc_code, f"{code}-pd")
    rd = _doc(DocStage.RD, doc_code, f"{code}-rd")
    pages = {DocStage.PD: _table_page(pd, pd_rows)}
    if rd_rows is not None:
        pages[DocStage.RD] = _table_page(rd, rd_rows)
    return evaluate_rule(
        _rule(code), object_id=f"OBJ-{code}", pages=pages,
        completeness=_completeness(), revision_pool=[pd, rd],
    ).finding.finding_status


@pytest.mark.parametrize("code", sorted(CASES))
def test_rule_is_executable_element_table(code: str) -> None:
    rule = _rule(code)
    assert rule["coverage"] == "executable"
    assert rule["extractor"]["type"] == "element_table"


@pytest.mark.parametrize("code", sorted(CASES))
def test_same_table_gives_no_difference(code: str) -> None:
    rows = CASES[code][1]
    assert _eval(code, rows, rows) is FindingStatus.AUTO_NO_DIFFERENCE


@pytest.mark.parametrize("code", sorted(CASES))
def test_changed_value_gives_candidate(code: str) -> None:
    rows = CASES[code][1]
    changed = (rows[0], (rows[1][0], CASES[code][2]))
    assert _eval(code, rows, changed) is FindingStatus.CANDIDATE


@pytest.mark.parametrize("code", sorted(CASES))
def test_changed_mark_set_is_not_auto_ok(code: str) -> None:
    rows = CASES[code][1]
    other = (rows[0], ("Х9-9", rows[1][1]))
    assert _eval(code, rows, other) not in {
        FindingStatus.AUTO_NO_DIFFERENCE, FindingStatus.CONFIRMED_VIOLATION,
    }
