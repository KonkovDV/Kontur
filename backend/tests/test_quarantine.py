"""Карантин скрытого теста. Этот тест защищает от утечки, а не от сбоя кода."""

from __future__ import annotations

from pathlib import Path

from kontur.evaluation.inventory import is_quarantined, quarantine_hits

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_quarantine_markers_are_detected() -> None:
    assert is_quarantined(Path("data/quarantine/РАЗМЕЧЕННЫЙ_TEST_213.zip"))
    assert is_quarantined(Path("data/work/obj-10/annotated_documents/x.json"))
    assert not is_quarantined(Path("data/work/obj-10/documents/АР-1.pdf"))


def test_real_organizer_names_are_detected() -> None:
    """Имена из поставки 15.09.2026: двойное подчёркивание и папка HIDDEN."""

    assert is_quarantined(Path("data/incoming/РАЗМЕЧЕННЫЙ_TEST__213.zip"))
    assert is_quarantined(
        Path("data/quarantine/РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213/QA_SUMMARY.json")
    )
    assert is_quarantined("РАЗМЕЧЕННЫЙ_test_hidden_организатор_213")


def test_public_train_is_not_quarantined() -> None:
    """Открытый train нельзя запирать в карантин: иначе учиться будет не на чем."""

    assert not is_quarantined(Path("data/work/РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203.zip"))
    assert not is_quarantined(Path("data/incoming/01_ПАКЕТ_УЧАСТНИКАМ_3_ОБЪЕКТА.tar"))
    assert not is_quarantined(Path("data/incoming/02_ЭТАЛОННАЯ_РАЗМЕТКА_И_МЕТОДИКА.tar"))


def test_quarantine_hits_lists_only_forbidden_paths() -> None:
    paths = [
        Path("data/incoming/РАЗМЕЧЕННЫЙ_TEST__213.zip"),
        Path("data/incoming/РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203.zip"),
    ]
    assert quarantine_hits(paths) == ["data/incoming/РАЗМЕЧЕННЫЙ_TEST__213.zip"]


def test_no_dataset_files_are_committed() -> None:
    """Исходники задачи и разметка не должны попадать в репозиторий."""

    tracked = [
        path
        for path in (REPO_ROOT / "data").rglob("*")
        if path.is_file() and path.suffix.lower() in {".zip", ".tar", ".pdf"}
    ]
    assert tracked == []
