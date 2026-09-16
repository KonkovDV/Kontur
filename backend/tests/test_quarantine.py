"""Карантин скрытого теста. Этот тест защищает от утечки, а не от сбоя кода."""

from __future__ import annotations

from pathlib import Path

from kontur.evaluation.inventory import is_quarantined

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_quarantine_markers_are_detected() -> None:
    assert is_quarantined(Path("data/quarantine/РАЗМЕЧЕННЫЙ_TEST_213.zip"))
    assert is_quarantined(Path("data/work/obj-10/annotated_documents/x.json"))
    assert not is_quarantined(Path("data/work/obj-10/documents/АР-1.pdf"))


def test_no_dataset_files_are_committed() -> None:
    """Исходники задачи и разметка не должны попадать в репозиторий."""

    tracked = [
        path
        for path in (REPO_ROOT / "data").rglob("*")
        if path.is_file() and path.suffix.lower() in {".zip", ".tar", ".pdf"}
    ]
    assert tracked == []
