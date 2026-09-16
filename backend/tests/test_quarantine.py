"""Карантин скрытого теста. Этот тест защищает от утечки, а не от сбоя кода."""

from __future__ import annotations

from pathlib import Path

import pytest

from kontur.evaluation.inventory import (
    QuarantineViolation,
    hash_archives,
    is_quarantined,
    quarantine_hits,
    require_path_open,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_quarantine_markers_are_detected() -> None:
    assert is_quarantined(Path("data/quarantine/РАЗМЕЧЕННЫЙ_TEST_213.zip"))
    assert is_quarantined(Path("data/incoming/РАЗМЕЧЕННЫЙ_TEST__213.zip"))
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


def test_annotated_documents_of_train_are_not_quarantined() -> None:
    """Каталог annotated_documents есть и у train, и у скрытого теста.

    Карантин — только скрытый тест и дерево data/quarantine/, иначе открытая
    разметка станет неотличима от запрещённой.
    """

    assert not is_quarantined(Path("data/work/obj-10/annotated_documents/x.json"))
    assert not is_quarantined(
        Path("data/work/РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203/annotated_documents/page.json")
    )
    assert is_quarantined(
        Path("data/quarantine/РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213/annotated_documents/x.json")
    )


def test_quarantine_hits_lists_only_forbidden_paths() -> None:
    paths = [
        Path("data/incoming/РАЗМЕЧЕННЫЙ_TEST__213.zip"),
        Path("data/incoming/РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203.zip"),
    ]
    assert quarantine_hits(paths) == [str(paths[0])]


def test_hash_archives_refuses_quarantine(tmp_path: Path) -> None:
    (tmp_path / "РАЗМЕЧЕННЫЙ_TEST__213.zip").write_bytes(b"x")
    with pytest.raises(QuarantineViolation, match="карантин"):
        hash_archives(tmp_path)


def test_hash_archives_refuses_nested_quarantine_name(tmp_path: Path) -> None:
    nested = tmp_path / "incoming" / "drop"
    nested.mkdir(parents=True)
    (nested / "РАЗМЕЧЕННЫЙ_TEST__213.zip").write_bytes(b"x")
    with pytest.raises(QuarantineViolation, match="карантин"):
        hash_archives(tmp_path)


def test_require_path_open_blocks_hidden_test_name(tmp_path: Path) -> None:
    hidden = tmp_path / "РАЗМЕЧЕННЫЙ_TEST__213.zip"
    hidden.write_bytes(b"x")
    with pytest.raises(QuarantineViolation):
        require_path_open(hidden)
    open_file = tmp_path / "10_Полярная_16.tar"
    open_file.write_bytes(b"x")
    assert require_path_open(open_file) == open_file


def test_hash_archives_still_pending_for_open_files(tmp_path: Path) -> None:
    (tmp_path / "10_Полярная_16.tar").write_bytes(b"x")
    with pytest.raises(NotImplementedError, match="Gate A"):
        hash_archives(tmp_path)


def test_no_dataset_files_are_committed() -> None:
    """Исходники задачи и разметка не должны попадать в репозиторий."""

    tracked = [
        path
        for path in (REPO_ROOT / "data").rglob("*")
        if path.is_file() and path.suffix.lower() in {".zip", ".tar", ".pdf", ".pptx"}
    ]
    assert tracked == []
