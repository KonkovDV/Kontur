"""Override имеет право поставить executable; каталог не затирает покрытие."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import compile_matrix  # noqa: E402

ROW = {
    "parameter_code": "PZ-001",
    "parameter_name": "Площадь застройки",
    "unit": "м²",
    "trigger": "Расхождение контуров > 0.",
    "criticality": "Критическое (приостановка работ)",
    "source_pd": "ТЭП",
    "source_rd": "Общие данные",
    "source_id": "БТИ",
}


def test_override_executable_coverage_survives_catalog_stamp() -> None:
    stamped = compile_matrix._stamp_catalog_fields({"coverage": "executable"}, ROW)
    assert stamped["coverage"] == "executable"
    assert stamped["name"] == "Площадь застройки"
    assert stamped["code"] == "PZ-001"


def test_unknown_coverage_in_override_is_rejected() -> None:
    with pytest.raises(ValueError, match="coverage"):
        compile_matrix._stamp_catalog_fields({"coverage": "почти_готово"}, ROW)


def test_skeleton_stays_extractor_missing() -> None:
    rule = compile_matrix.skeleton(ROW)
    assert rule["coverage"] == "extractor_missing"
