"""Пакетный прогон на синтетике. Скрытый тест и MIXED не становятся эталоном."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from kontur.cli.run_package import (
    PackageFile,
    _extended_path,
    _field_row,
    _page_rows,
    _read_bytes,
    run_directory,
)
from kontur.domain.models import DocStage
from kontur.evaluation.dataset_package import HIDDEN_TEST_OBJECT_IDS
from kontur.evaluation.demo_kit import demo_sheet_files
from kontur.infrastructure.pdfium_tokens import file_sha256
from kontur.infrastructure.synthetic_pdf import cyrillic_pdf


def _write_kit(root: Path, object_id: str) -> None:
    folders = {DocStage.PD: "ПД", DocStage.RD: "РД", DocStage.ID: "ИД"}
    for file_id, stage, _filename, payload in demo_sheet_files():
        folder = root / object_id / folders[stage]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{file_id}.pdf").write_bytes(payload)


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH только на Windows")
def test_long_windows_path_is_readable(tmp_path: Path) -> None:
    leaf = "d" * 80
    folder = tmp_path
    for _ in range(4):
        folder = folder / leaf
    target = _extended_path(folder / "sheet.pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"%PDF-1.4 long")
    plain = Path(str(target)[4:])
    assert len(str(plain)) > 260
    assert _read_bytes(plain) == b"%PDF-1.4 long"


def test_folder_package_writes_schema_valid_draft(tmp_path: Path) -> None:
    source = tmp_path / "in"
    out = tmp_path / "out"
    object_id = "OBJ-PACK-SYNTH"
    _write_kit(source, object_id)
    hidden = next(iter(HIDDEN_TEST_OBJECT_IDS))
    hidden_dir = source / hidden / "ПД"
    hidden_dir.mkdir(parents=True)
    (hidden_dir / "secret.pdf").write_bytes(cyrillic_pdf((("шифр", 20.0, 20.0),)))

    report = run_directory(source, out)

    assert report["closes_gate_i"] is False
    assert report["closes_gate_j"] is False
    assert report["mode"] == "folders"
    assert report["failures"] == []
    assert [row["object_id"] for row in report["skipped"]] == [hidden]
    assert not list(out.glob(f"*{hidden}*"))
    written = report["objects"]
    assert len(written) == 1
    row = written[0]
    assert row["n_files"] == 4
    assert row["violation_count"] == 0
    assert row["process_state"] == "READY"
    submission = json.loads((out / row["submission"]).read_text(encoding="utf-8"))
    protocol = json.loads((out / row["protocol"]).read_text(encoding="utf-8"))
    documents = json.loads((out / row["documents"]).read_text(encoding="utf-8"))
    assert submission["object_id"] == object_id
    assert submission["checks"]
    assert all(item["location"].strip() for item in submission["checks"])
    assert "AUTO_NO_DIFFERENCE" not in json.dumps(protocol)
    assert "preliminary_no_difference" not in protocol["sections"]
    assert protocol["violation_count"] == 0
    assert protocol["sections"]["confirmed"] == []
    names = {item["file_id"] for item in documents["files"]}
    assert names == {"f-pd-draft", "f-pd", "f-rd", "f-id"}
    fields = (out / row["fields"]).read_text(encoding="utf-8").splitlines()
    assert len(fields) == 4
    assert all(json.loads(line)["room"] is None for line in fields)
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["file_timeout_seconds"] == 600


def test_run_manifest_uses_image_sha_without_git(tmp_path: Path, monkeypatch) -> None:
    sha = "a" * 40
    monkeypatch.setenv("KONTUR_GIT_SHA", sha)
    from kontur.evaluation.agent_dumps import git_sha

    monkeypatch.setattr(
        "kontur.cli.run_package.git_sha",
        lambda _root=None: git_sha(tmp_path),
    )
    source = tmp_path / "in"
    out = tmp_path / "out"
    _write_kit(source, "OBJ-PACK-SHA")
    report = run_directory(source, out)
    assert report["failures"] == []
    manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["versions"]["git_sha"] == sha


def test_index_skips_mixed_stage(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    payload = cyrillic_pdf((("лист", 20.0, 40.0),))
    (source / "pd.pdf").write_bytes(payload)
    (source / "mixed.pdf").write_bytes(payload)
    digest = file_sha256(payload)
    rows = [
        {"object_id": "OBJ-PACK-INDEX", "file_id": "pd-1", "stage": "PD", "path": "pd.pdf"},
        {
            "object_id": "OBJ-PACK-INDEX",
            "file_id": "mixed-1",
            "stage": "RD_ID_MIXED",
            "path": "mixed.pdf",
        },
        {"object_id": "OBJ-PACK-INDEX", "stage": "PD", "path": "../outside.pdf"},
    ]
    (source / "files_index.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    report = run_directory(source, tmp_path / "out")
    assert report["mode"] == "files_index"
    assert report["failures"] == []
    reasons = {item["reason"] for item in report["skipped"]}
    assert reasons == {"unmapped_stage", "path_escapes_input"}
    documents = json.loads(
        (tmp_path / "out" / "documents_OBJ-PACK-INDEX.json").read_text(encoding="utf-8")
    )
    assert [item["file_id"] for item in documents["files"]] == ["pd-1"]
    assert documents["files"][0]["file_hash"] == digest


def test_field_and_page_rows_pass_the_package_timeout(tmp_path: Path, monkeypatch) -> None:
    seen: list[float] = []

    def fake(_parser: object, _raw: bytes, *, timeout_s: float = 30.0) -> object:
        seen.append(timeout_s)
        raise ValueError("stop")

    monkeypatch.setattr("kontur.cli.run_package.run_pdf_parse_sync", fake)
    monkeypatch.setenv("KONTUR_PDF_PARSE_TIMEOUT_S", "600")
    item = PackageFile("f-1", DocStage.PD, tmp_path / "a.pdf")
    _field_row(item, b"%PDF", "a" * 64, "OBJ-PACK-TIMEOUT")
    assert _page_rows(item, b"%PDF", "OBJ-PACK-TIMEOUT") == []
    assert seen == [600.0, 600.0]


def test_pages_text_writes_words_with_bbox_and_engine(tmp_path: Path) -> None:
    source = tmp_path / "in"
    out = tmp_path / "out"
    _write_kit(source, "OBJ-PACK-PAGES")
    report = run_directory(source, out, pages_text=True)
    assert report["failures"] == []
    path = out / "pages_text_OBJ-PACK-PAGES.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows
    for row in rows:
        assert set(row) >= {"object_id", "file_id", "page", "text", "bbox", "engine"}
        assert row["engine"] in {"vector", "ocr"}
        assert len(row["bbox"]) == 4
        assert row["text"].strip()
