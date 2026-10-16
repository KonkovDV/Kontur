"""Пример JSON ответа и протокола из синтетического учебного комплекта.

Комплект собирается `demo_sheet_files()`: документы организатора сюда не входят.
Два исхода:

* `unattended/` — пакетный прогон без инспектора, как `run_package`;
* `after_etalon_select/` — инспектор назначил `f-pd` эталоном, решения по
  находкам ещё нет. Автомат пишет `CANDIDATE`, не `CONFIRMED_VIOLATION`.

Запуск из корня клона: `python scripts/export_submission_example.py`.
Проверка без записи: `python scripts/export_submission_example.py --check`
(собирает во временный каталог и сравнивает с файлами в git; отличается только
`versions.git_sha`, он от проверки исключён).

Сборка воспроизводима: в PDF комплекта фиксируются CreationDate и /ID, у
протоколов постоянный protocol_id. Два запуска подряд дают одинаковые байты.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from kontur.application.protocol import assemble_protocol, protocol_for_http  # noqa: E402
from kontur.application.runtime import ProcessRecord, ProcessWorkspace  # noqa: E402
from kontur.cli.run_package import (  # noqa: E402
    _schema_validator,
    run_directory,
    submission_from_record,
)
from kontur.domain.models import DocStage  # noqa: E402
from kontur.domain.state_machines import Actor  # noqa: E402
from kontur.domain.statuses import ProcessState  # noqa: E402
from kontur.evaluation import demo_kit  # noqa: E402
from kontur.evaluation.agent_dumps import git_sha, repo_root  # noqa: E402
from kontur.evaluation.demo_kit import (  # noqa: E402
    DEMO_OBJECT_ID,
    ETALON_FILE_ID,
    install_demo_kit,
)
from kontur.evaluation.submission_pack import build_input_manifest  # noqa: E402
from kontur.infrastructure.matrix.registry import FileRuleRegistry  # noqa: E402

TARGET = ROOT / "submission" / "05-additional" / "examples"
_FILES = (
    ("unattended", "submission.json"),
    ("unattended", "protocol.json"),
    ("after_etalon_select", "submission.json"),
    ("after_etalon_select", "protocol.json"),
)
_CREATION_DATE = re.compile(rb"/CreationDate\(D:\d{14}[^)]*\)")
_FIXED_DATE = b"/CreationDate(D:20260101000000+00'00')"
_TRAILER_ID = re.compile(rb"/ID\[<[0-9A-Fa-f]{32}><[0-9A-Fa-f]{32}>\]")
_FIXED_ID = b"/ID[<" + b"0" * 32 + b"><" + b"0" * 32 + b">]"
_SHEETS = demo_kit.demo_sheet_files


def reproducible_pdf(payload: bytes) -> bytes:
    """Постоянные CreationDate и /ID той же длины: смещения xref не сдвигаются."""

    fixed, dates = _CREATION_DATE.subn(_FIXED_DATE, payload)
    if dates and len(fixed) != len(payload):
        raise SystemExit("CreationDate другой длины: xref PDF сдвинулся бы")
    fixed = _TRAILER_ID.sub(_FIXED_ID, fixed)
    return fixed


def reproducible_sheets() -> tuple[tuple[str, DocStage, str, bytes], ...]:
    return tuple(
        (file_id, stage, name, reproducible_pdf(payload))
        for file_id, stage, name, payload in _SHEETS()
    )
_FOLDERS = {DocStage.PD: "ПД", DocStage.RD: "РД", DocStage.ID: "ИД"}
_INSPECTOR = Actor("inspector-demo", is_human=True)


def _write(folder: Path, name: str, payload: dict[str, object]) -> None:
    if name == "protocol.json":
        payload = {**payload, "protocol_id": f"protocol-example-{folder.name}"}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _unattended(target: Path) -> None:
    with tempfile.TemporaryDirectory() as raw:
        work = Path(raw)
        source = work / "in"
        for file_id, stage, _filename, payload in reproducible_sheets():
            folder = source / DEMO_OBJECT_ID / _FOLDERS[stage]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{file_id}.pdf").write_bytes(payload)
        out = work / "out"
        report = run_directory(source, out)
        objects = report["objects"]
        if not isinstance(objects, list) or len(objects) != 1:
            raise SystemExit("ожидался один объект учебного комплекта")
        row = objects[0]
        if not isinstance(row, dict):
            raise SystemExit("строка объекта не словарь")
        for key in ("submission", "protocol"):
            payload = json.loads((out / str(row[key])).read_text(encoding="utf-8"))
            _write(target / "unattended", f"{key}.json", payload)


def _protocol(record: ProcessRecord, registry: FileRuleRegistry) -> dict[str, object]:
    files = [{"file_id": item.file_id, "file_hash": item.file_hash} for item in record.files]
    manifest = build_input_manifest(files)
    versions = {
        "git_sha": git_sha(repo_root()),
        "matrix_version": registry.matrix_version,
        "dataset_version": record.dataset_version,
        "model_version": record.model_version,
    }
    return protocol_for_http(
        assemble_protocol(
            protocol_id=f"protocol-{record.process_id}",
            object_id=record.object_id,
            findings=tuple(record.findings.values()),
            completeness=record.completeness,
            files=files,
            versions=versions,
            process_state=ProcessState.READY,
            input_manifest_hash=str(manifest["manifest_hash"]),
        )
    )


def _after_select(target: Path) -> None:
    registry = FileRuleRegistry()
    workspace = ProcessWorkspace()
    record = install_demo_kit(workspace, DEMO_OBJECT_ID)
    workspace.select_revision(
        record.process_id,
        ETALON_FILE_ID,
        actor=_INSPECTOR,
        comment="Учебный комплект: утверждённая редакция тома, черновик не эталон.",
    )
    submission, dropped = submission_from_record(record, registry)
    if dropped:
        raise SystemExit(f"строки ответа отброшены: {dropped}")
    _schema_validator("submission.schema.json").validate(submission)
    protocol = _protocol(record, registry)
    _schema_validator("protocol.schema.json").validate(protocol)
    _write(target / "after_etalon_select", "submission.json", submission)
    _write(target / "after_etalon_select", "protocol.json", protocol)


def build(target: Path) -> None:
    """Собрать оба исхода в ``target``. Комплект — с воспроизводимыми PDF."""

    demo_kit.demo_sheet_files = reproducible_sheets
    try:
        _unattended(target)
        _after_select(target)
    finally:
        demo_kit.demo_sheet_files = _SHEETS


def _without_git_sha(raw: bytes) -> object:
    payload = json.loads(raw)
    versions = payload.get("versions") if isinstance(payload, dict) else None
    if isinstance(versions, dict):
        versions.pop("git_sha", None)
    return payload


def drift(target: Path = TARGET) -> list[str]:
    """Файлы примеров, отличные от свежей сборки (без учёта versions.git_sha)."""

    with tempfile.TemporaryDirectory() as raw:
        fresh = Path(raw)
        build(fresh)
        changed: list[str] = []
        for folder, name in _FILES:
            committed = target / folder / name
            built = fresh / folder / name
            if not committed.is_file() or _without_git_sha(
                committed.read_bytes()
            ) != _without_git_sha(built.read_bytes()):
                changed.append(f"{folder}/{name}")
        return changed


def main() -> int:
    if sys.argv[1:] == ["--check"]:
        changed = drift()
        for name in changed:
            print(f"пример расходится со сборкой: {name}")
        if changed:
            print("перезапустите python scripts/export_submission_example.py")
            return 1
        print("examples: совпадают со сборкой")
        return 0
    build(TARGET)
    print(f"examples: {TARGET.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
