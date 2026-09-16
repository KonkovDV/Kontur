"""Манифест поставки: карантин, хеши, изоляция по объектам."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kontur.evaluation.dataset_package import (
    HIDDEN_TEST_OBJECT_IDS,
    LABELED_TRAIN_OBJECT_IDS,
    MANIFEST_PATH,
    PackageEntry,
    QuarantineViolation,
    is_hidden_test_object,
    load_entries,
    object_ids,
    pending_hashes,
    require_labeled_train_object,
    require_open,
    total_size_kb,
    usable_for_experiments,
)
from kontur.evaluation.inventory import is_quarantined

REPO_ROOT = Path(__file__).resolve().parents[2]
OBJECTS_PATH = REPO_ROOT / "data" / "dataset" / "objects.json"
HEX_DIGITS = frozenset("0123456789abcdef")


def test_manifest_path_points_into_repository() -> None:
    assert MANIFEST_PATH == REPO_ROOT / "data" / "dataset" / "package_manifest.json"
    assert MANIFEST_PATH.is_file()


def test_hidden_test_stays_quarantined() -> None:
    hidden = [entry for entry in load_entries() if entry.kind == "annotated_hidden_test"]
    assert hidden, "в манифесте нет записи о скрытом тесте"
    for entry in hidden:
        assert entry.is_quarantined
        with pytest.raises(QuarantineViolation):
            require_open(entry)


def test_quarantine_detector_agrees_with_manifest() -> None:
    """Детектор имён и манифест не должны расходиться ни в одну сторону."""

    for entry in load_entries():
        assert is_quarantined(entry.name) == entry.is_quarantined, entry.name


def test_usable_set_excludes_quarantine() -> None:
    entries = load_entries()
    usable = usable_for_experiments(entries)
    assert usable
    assert all(not entry.is_quarantined for entry in usable)
    assert len(usable) < len(entries)


def test_train_package_is_open() -> None:
    train = [entry for entry in load_entries() if entry.kind == "annotated_train"]
    assert train, "в манифесте нет открытого train"
    for entry in train:
        assert require_open(entry) is entry


def test_hashes_are_either_pending_or_valid_sha256() -> None:
    entries = load_entries()
    for entry in entries:
        if entry.sha256 is not None:
            assert len(entry.sha256) == 64, entry.name
            assert set(entry.sha256.lower()) <= HEX_DIGITS, entry.name
    assert set(pending_hashes(entries)) <= {entry.name for entry in entries}
    assert pending_hashes(entries), "Gate A не закрыт: SHA-256 ещё не внесены"


def test_total_volume_is_plausible_for_disk_budget() -> None:
    """Поставка — десятки ГБ: бюджет диска считается по манифесту, а не на глаз."""

    assert total_size_kb(load_entries()) > 50_000_000


def test_objects_file_is_isolated_by_object_id() -> None:
    payload = json.loads(OBJECTS_PATH.read_text(encoding="utf-8"))
    ids = [item["object_id"] for item in payload["objects"]]
    assert ids
    assert len(ids) == len(set(ids)), "дубликат object_id: разбиение перестанет быть изоляцией"
    assert set(object_ids(load_entries())) <= set(ids)
    for item in payload["objects"]:
        assert item["split"] in {None, "train", "validation"}


def test_hidden_kind_cannot_be_loaded_as_open(tmp_path: Path) -> None:
    payload = {
        "entries": [
            {
                "name": "РАЗМЕЧЕННЫЙ_TEST__213.zip",
                "kind": "annotated_hidden_test",
                "access": "open",
                "object_id": None,
                "size_kb": 1,
                "sha256": None,
                "notes": "",
            }
        ]
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="quarantine"):
        load_entries(path)


def test_usable_set_excludes_name_detector_even_if_manifest_tampered() -> None:
    """RT-A: правка access=open на скрытом тесте не должна пускать его в эксперимент."""

    tampered = PackageEntry(
        name="РАЗМЕЧЕННЫЙ_TEST__213.zip",
        kind="annotated_hidden_test",
        access="open",
        object_id=None,
        size_kb=1,
        sha256=None,
        notes="tamper",
    )
    with pytest.raises(QuarantineViolation):
        require_open(tampered)
    assert usable_for_experiments([tampered]) == ()


def test_hidden_object_id_is_blocked_even_without_filename_markers() -> None:
    """Документы Речникова открыты, ответы — нет. Allowlist, не blocklist имён."""

    assert HIDDEN_TEST_OBJECT_IDS == {"OBJ-RECHNIKOV-7-7"}
    assert is_hidden_test_object("OBJ-RECHNIKOV-7-7")
    with pytest.raises(QuarantineViolation):
        require_labeled_train_object("OBJ-RECHNIKOV-7-7")
    for object_id in LABELED_TRAIN_OBJECT_IDS:
        assert require_labeled_train_object(object_id) == object_id
    with pytest.raises(ValueError, match="allowlist"):
        require_labeled_train_object("10_Полярная_25_СОШ1100к7")
