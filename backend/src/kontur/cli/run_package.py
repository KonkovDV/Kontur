"""Пакетный прогон комплекта: JSON участника и черновик протокола.

`python -m kontur.cli.run_package --input <dir> --out <dir>`

Режимы входа: `files_index.jsonl` либо папки `<объект>/{ПД|РД|ИД}`.
Берутся все PDF объекта. `RD_ID_MIXED` становится РД только по метке «РД»
в имени или шифре и ИД по «АОСР» на первой странице. Скрытый тест
пропускается. Автомат не пишет CONFIRMED_VIOLATION. AUTO_NO_DIFFERENCE
на провод протокола не попадает. Гейты I/J/K/L этим модулем не закрываются.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Mapping, Sequence
from importlib import import_module
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from kontur.application.passport import read_passport
from kontur.application.protocol import assemble_protocol, protocol_for_http
from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.domain.geometry import bbox_from_polygon
from kontur.domain.models import DocStage, EvidenceGroup, Finding
from kontur.domain.statuses import Completeness, ProcessState
from kontur.evaluation.agent_dumps import git_sha, repo_root
from kontur.evaluation.dataset_package import is_hidden_test_object
from kontur.evaluation.inventory import QuarantineViolation, is_quarantined, require_path_open
from kontur.evaluation.submission import build_check, build_submission
from kontur.evaluation.submission_pack import build_input_manifest
from kontur.infrastructure.matrix.registry import FileRuleRegistry
from kontur.infrastructure.pdf_guard import (
    PdfParseTimeoutError,
    pdf_parse_timeout_s,
    run_pdf_parse_sync,
)
from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes, file_sha256, flatten_tokens

FILE_TIMEOUT_S = 600.0
RUN_SCHEMA = "kontur.run_package.v1"
_INDEX_NAMES = ("files_index.jsonl", "data/files_index.jsonl")
_STAGE_NAMES: dict[str, DocStage] = {
    "pd": DocStage.PD,
    "rd": DocStage.RD,
    "id": DocStage.ID,
    "пд": DocStage.PD,
    "рд": DocStage.RD,
    "ид": DocStage.ID,
}
_UNMAPPED_STAGE = frozenset({"rd_id_mixed", "unknown", "mixed"})
_MIXED_STAGE = frozenset({"rd_id_mixed", "mixed"})
_RD_MARK = re.compile(r"(?<!\w)рд(?!\w)")
_SLUG = re.compile(r'[<>:"/\\|?*\s]+')


def _slug(object_id: str) -> str:
    cleaned = _SLUG.sub("_", object_id).strip("._")
    return cleaned or "object"


def _stage_token(raw: str) -> DocStage | None:
    token = raw.strip().casefold().replace(" ", "")
    if token in _UNMAPPED_STAGE:
        return None
    if token in _STAGE_NAMES:
        return _STAGE_NAMES[token]
    tail = token.rsplit("_", 1)[-1].rsplit("-", 1)[-1]
    if tail in _STAGE_NAMES:
        return _STAGE_NAMES[tail]
    return None


def _has_rd_mark(text: str) -> bool:
    return _RD_MARK.search(text.casefold()) is not None


def _first_page_text(path: Path) -> str:
    """Текст первой страницы. Ошибка чтения не роняет весь комплект."""

    try:
        pdfium = import_module("pypdfium2")
        document = pdfium.PdfDocument(_read_bytes(path))
    except (OSError, RuntimeError, ValueError):
        return ""
    try:
        if len(document) < 1:
            return ""
        page = document[0]
        textpage = page.get_textpage()
        try:
            return str(textpage.get_text_bounded() or "")
        finally:
            textpage.close()
            page.close()
    except (OSError, RuntimeError, ValueError):
        return ""
    finally:
        document.close()


def _stage_from_mixed(path: Path, cipher: str) -> tuple[DocStage | None, str]:
    """РД по метке в имени или шифре. ИД по «АОСР» на листе 1. Иначе не стадия."""

    if _has_rd_mark(path.name) or _has_rd_mark(cipher):
        return DocStage.RD, "filename_or_cipher_rd"
    try:
        page = _first_page_text(path)
    except OSError:
        return None, "page1_unreadable"
    if "аоср" in page.casefold():
        return DocStage.ID, "page1_aosr"
    return None, "no_rd_or_aosr"


def _inside(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    base = root.resolve()
    resolved.relative_to(base)
    return resolved


def _index_path(root: Path) -> Path | None:
    for name in _INDEX_NAMES:
        path = root / name
        if path.is_file() and not is_quarantined(path):
            return path
    return None


def _extended_path(path: Path) -> Path:
    """Префикс \\\\?\\ для путей длиннее MAX_PATH. Обычный open их не видит."""

    text = str(path)
    if text.startswith("\\\\?\\"):
        return path
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def _read_bytes(path: Path) -> bytes:
    require_path_open(path)
    try:
        return path.read_bytes()
    except OSError as exc:
        if sys.platform != "win32" or exc.errno != 2:
            raise
        return _extended_path(path).read_bytes()


class PackageFile:
    def __init__(self, file_id: str, stage: DocStage, path: Path) -> None:
        self.file_id = file_id
        self.stage = stage
        self.path = path


def _unique_id(stem: str, used: set[str], digest: str) -> str:
    candidate = stem or "file"
    if candidate not in used:
        used.add(candidate)
        return candidate
    suffixed = f"{candidate}-{digest[:8]}"
    used.add(suffixed)
    return suffixed


def discover_folders(root: Path) -> tuple[dict[str, list[PackageFile]], list[dict[str, str]]]:
    """Папки стадий. Скрытый объект не открывается."""

    skipped: list[dict[str, str]] = []
    objects: dict[str, list[PackageFile]] = {}

    def take(object_id: str, folder: Path) -> None:
        if is_hidden_test_object(object_id):
            skipped.append({"object_id": object_id, "reason": "hidden_test"})
            return
        files = _pdfs_in_object(folder)
        if files:
            objects[object_id] = files

    children = [
        path for path in sorted(root.iterdir()) if path.is_dir() and not is_quarantined(path)
    ]
    staged_children = [path for path in children if _has_stage_dir(path)]
    if staged_children:
        for child in staged_children:
            take(child.name, child)
        return objects, skipped
    if _has_stage_dir(root):
        take(root.name, root)
    return objects, skipped


def _has_stage_dir(folder: Path) -> bool:
    return any(path.is_dir() and _stage_token(path.name) is not None for path in folder.iterdir())


def _pdfs_in_object(folder: Path) -> list[PackageFile]:
    used: set[str] = set()
    found: list[PackageFile] = []
    for stage_dir in sorted(path for path in folder.iterdir() if path.is_dir()):
        stage = _stage_token(stage_dir.name)
        if stage is None or is_quarantined(stage_dir):
            continue
        for path in sorted(stage_dir.rglob("*")):
            if not path.is_file() or is_quarantined(path):
                continue
            suffix = path.suffix.lower()
            if suffix not in {".pdf", ".docx", ".xml"}:
                continue
            digest = file_sha256(_read_bytes(path))
            file_id = _unique_id(path.stem, used, digest)
            found.append(PackageFile(file_id, stage, path))
    return found


def discover_index(
    root: Path, index: Path
) -> tuple[dict[str, list[PackageFile]], list[dict[str, str]], list[dict[str, str]]]:
    """Строки индекса. MIXED становится РД или ИД только по явной метке."""

    skipped: list[dict[str, str]] = []
    resolutions: list[dict[str, str]] = []
    grouped: dict[str, list[PackageFile]] = {}
    used: dict[str, set[str]] = {}
    require_path_open(index)
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"files_index:{number}: ожидался объект")
        object_id = str(payload.get("object_id") or "").strip()
        if not object_id:
            raise ValueError(f"files_index:{number}: нет object_id")
        if is_hidden_test_object(object_id):
            skipped.append({"object_id": object_id, "reason": "hidden_test", "line": str(number)})
            continue
        stage_raw = str(payload.get("stage") or payload.get("doc_stage") or "")
        stage = _stage_token(stage_raw)
        folded_stage = stage_raw.strip().casefold().replace(" ", "")
        mixed = stage is None and folded_stage in _MIXED_STAGE
        if stage is None and not mixed:
            skipped.append(
                {
                    "object_id": object_id,
                    "reason": "unmapped_stage",
                    "stage": stage_raw,
                    "line": str(number),
                }
            )
            continue
        cipher = " ".join(
            str(payload.get(key) or "")
            for key in ("document_code", "cipher", "code", "filename")
        )
        relative = str(
            payload.get("source_relative_path")
            or payload.get("path")
            or payload.get("output_pdf")
            or ""
        ).replace("\\", "/")
        if not relative:
            raise ValueError(f"files_index:{number}: нет пути")
        try:
            path = _inside(root, root / relative)
        except ValueError:
            skipped.append(
                {"object_id": object_id, "reason": "path_escapes_input", "line": str(number)}
            )
            continue
        if is_quarantined(path) or not path.is_file():
            skipped.append({"object_id": object_id, "reason": "missing_file", "line": str(number)})
            continue
        if mixed:
            stage, basis = _stage_from_mixed(path, cipher)
            if stage is None:
                skipped.append(
                    {
                        "object_id": object_id,
                        "reason": "unmapped_stage",
                        "stage": stage_raw,
                        "stage_basis": basis,
                        "line": str(number),
                    }
                )
                continue
            resolutions.append(
                {
                    "object_id": object_id,
                    "file_id": str(payload.get("file_id") or "").strip() or path.stem,
                    "from_stage": stage_raw,
                    "stage": stage.value,
                    "stage_basis": basis,
                    "line": str(number),
                }
            )
        assert stage is not None
        digest = file_sha256(_read_bytes(path))
        file_id = str(payload.get("file_id") or "").strip() or path.stem
        bucket = used.setdefault(object_id, set())
        if file_id in bucket:
            file_id = _unique_id(file_id, bucket, digest)
        else:
            bucket.add(file_id)
        grouped.setdefault(object_id, []).append(PackageFile(file_id, stage, path))
    return grouped, skipped, resolutions


def _schema_validator(schema_name: str) -> Draft202012Validator:
    schemas = repo_root() / "contracts" / "schemas"
    registry: Registry[dict[str, object]] = Registry()
    for path in schemas.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(data)
        for ident in (str(data.get("$id") or path.name), path.name, f"./{path.name}"):
            registry = registry.with_resource(ident, resource)
    schema = json.loads((schemas / schema_name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def _location_for(finding: Finding, group: EvidenceGroup | None) -> str | None:
    if group is not None and group.fragments:
        return None
    text = finding.rationale.strip()
    return text or "объект"


def submission_from_record(
    record: ProcessRecord,
    registry: FileRuleRegistry,
) -> tuple[dict[str, object], list[dict[str, str]]]:
    """Собрать checks. Строка без доказательства нарушения в ответ не попадает."""

    codes = registry.all_codes()
    rules = {code: registry.get(code) for code in codes}
    checks = []
    dropped: list[dict[str, str]] = []
    for finding in record.findings.values():
        group = None
        if finding.evidence_group_id is not None:
            group = record.evidence_groups.get(finding.evidence_group_id)
        try:
            checks.append(
                build_check(
                    finding,
                    group,
                    location=_location_for(finding, group),
                    rule=rules.get(finding.rule_code),
                    known_codes=codes,
                )
            )
        except ValueError as exc:
            dropped.append({"rule_code": finding.rule_code, "reason": str(exc)})
    return build_submission(record.object_id, checks, known_codes=codes), dropped


def _field_row(item: PackageFile, raw: bytes, digest: str, object_id: str) -> dict[str, object]:
    cipher = None
    revision = None
    sheet = None
    parse_error = None
    suffix = item.path.suffix.lower()
    if suffix in {".docx", ".xml"}:
        return {
            "object_id": object_id,
            "file_id": item.file_id,
            "doc_stage": item.stage.value,
            "cipher": None,
            "revision": None,
            "sheet": None,
            "room": None,
            "parse_error": f"UNSUPPORTED_FORMAT: сверка читает PDF, {suffix} без разбора",
        }
    try:
        document = run_pdf_parse_sync(
            extract_pdf_bytes, raw, timeout_s=pdf_parse_timeout_s()
        )
        tokens = flatten_tokens(document)
        last = document.pages[-1]
        passport = read_passport(
            tokens,
            file_id=item.file_id,
            file_hash=digest,
            filename=item.path.name,
            pages=len(document.pages),
            layer_kind=document.layer_kind,
            rotate=last.frame.rotate,
            object_id=object_id,
        )
        cipher = passport.document_code
        revision = passport.revision
        sheet = passport.sheet
    except (PdfParseTimeoutError, ValueError, OSError) as exc:
        cipher = None
        parse_error = str(exc)
    return {
        "object_id": object_id,
        "file_id": item.file_id,
        "doc_stage": item.stage.value,
        "cipher": cipher,
        "revision": revision,
        "sheet": sheet,
        "room": None,
        "parse_error": parse_error,
    }


def _page_rows(item: PackageFile, raw: bytes, object_id: str) -> list[dict[str, object]]:
    if item.path.suffix.lower() in {".docx", ".xml"}:
        return []
    rows: list[dict[str, object]] = []
    try:
        document = run_pdf_parse_sync(
            extract_pdf_bytes, raw, timeout_s=pdf_parse_timeout_s()
        )
    except (PdfParseTimeoutError, ValueError, OSError):
        return rows
    for token in flatten_tokens(document):
        if not token.text.strip():
            continue
        box = bbox_from_polygon(token.polygon_norm)
        rows.append(
            {
                "object_id": object_id,
                "file_id": item.file_id,
                "page": token.page,
                "text": token.text,
                "bbox": [box[0], box[1], box[2], box[3]],
                "engine": token.engine.value,
            }
        )
    return rows


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _completeness(files: Sequence[PackageFile]) -> dict[DocStage, Completeness]:
    present = {item.stage for item in files}
    return {
        stage: Completeness.UPLOADED if stage in present else Completeness.MISSING
        for stage in DocStage
    }


def run_object(
    object_id: str,
    files: Sequence[PackageFile],
    out_dir: Path,
    *,
    pages_text: bool,
    registry: FileRuleRegistry,
) -> dict[str, object]:
    """Прогнать матрицу и записать JSON. Подтверждений инспектора нет."""

    started = time.perf_counter()
    stage_seconds: dict[str, float] = {stage.value: 0.0 for stage in DocStage}
    workspace = ProcessWorkspace()
    record = workspace.create(object_id, _completeness(files))
    loaded: list[tuple[PackageFile, bytes, str]] = []
    for item in files:
        tick = time.perf_counter()
        raw = _read_bytes(item.path)
        stage_seconds[item.stage.value] += time.perf_counter() - tick
        digest = file_sha256(raw)
        workspace.attach_file(
            record,
            AcceptedFile(
                file_id=item.file_id,
                file_hash=digest,
                filename=item.path.name,
                doc_stage=item.stage,
                size_bytes=len(raw),
            ),
        )
        workspace.keep_blob(record, item.file_id, raw)
        loaded.append((item, raw, digest))
    pipeline_started = time.perf_counter()
    report = workspace.run_matrix_pipeline(record)
    pipeline_seconds = time.perf_counter() - pipeline_started
    manifest_files = [
        {"file_id": item.file_id, "file_hash": digest} for item, _raw, digest in loaded
    ]
    manifest = build_input_manifest(manifest_files)
    submission, dropped = submission_from_record(record, registry)
    _schema_validator("submission.schema.json").validate(submission)
    versions = {
        "git_sha": git_sha(repo_root()),
        "matrix_version": registry.matrix_version,
        "dataset_version": record.dataset_version,
        "model_version": record.model_version,
    }
    protocol = protocol_for_http(
        assemble_protocol(
            protocol_id=f"protocol-{record.process_id}",
            object_id=object_id,
            findings=tuple(record.findings.values()),
            completeness=record.completeness,
            files=[
                {"file_id": row["file_id"], "file_hash": row["file_hash"]} for row in manifest_files
            ],
            versions=versions,
            process_state=ProcessState.READY,
            input_manifest_hash=str(manifest["manifest_hash"]),
        )
    )
    _schema_validator("protocol.schema.json").validate(protocol)
    slug = _slug(object_id)
    submission_name = f"submission_{slug}.json"
    protocol_name = f"protocol_{slug}.json"
    documents_name = f"documents_{slug}.json"
    fields_name = f"fields_{slug}.jsonl"
    _write_json(out_dir / submission_name, submission)
    _write_json(out_dir / protocol_name, protocol)
    _write_json(
        out_dir / documents_name,
        {
            "object_id": object_id,
            "files": [
                {
                    "file_id": item.file_id,
                    "file_hash": digest,
                    "filename": item.path.name,
                    "doc_stage": item.stage.value,
                    "size_bytes": len(raw),
                }
                for item, raw, digest in loaded
            ],
        },
    )
    field_lines = [
        json.dumps(_field_row(item, raw, digest, object_id), ensure_ascii=False)
        for item, raw, digest in loaded
    ]
    (out_dir / fields_name).write_text("\n".join(field_lines) + "\n", encoding="utf-8")
    pages_name = None
    if pages_text:
        pages_name = f"pages_text_{slug}.jsonl"
        page_lines = [
            json.dumps(row, ensure_ascii=False)
            for item, raw, _digest in loaded
            for row in _page_rows(item, raw, object_id)
        ]
        (out_dir / pages_name).write_text(
            ("\n".join(page_lines) + "\n") if page_lines else "",
            encoding="utf-8",
        )
    return {
        "object_id": object_id,
        "n_files": len(loaded),
        "rules_evaluated": report.rules_evaluated,
        "parse_errors": list(report.parse_errors),
        "dropped_checks": dropped,
        "stage_read_seconds": stage_seconds,
        "pipeline_seconds": round(pipeline_seconds, 3),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "input_manifest_hash": manifest["manifest_hash"],
        "process_state": record.process_state.value,
        "submission": submission_name,
        "protocol": protocol_name,
        "documents": documents_name,
        "fields": fields_name,
        "pages_text": pages_name,
        "violation_count": protocol["violation_count"],
    }


def run_directory(source: Path, out_dir: Path, *, pages_text: bool = False) -> dict[str, object]:
    """Разобрать вход и записать пакет. Не подтверждает находки."""

    _ensure_file_timeout()
    root = require_path_open(source)
    if not root.is_dir():
        raise ValueError(f"{root}: не каталог")
    out_dir.mkdir(parents=True, exist_ok=True)
    index = _index_path(root)
    resolutions: list[dict[str, str]] = []
    if index is not None:
        grouped, skipped, resolutions = discover_index(root, index)
        mode = "files_index"
    else:
        grouped, skipped = discover_folders(root)
        mode = "folders"
    registry = FileRuleRegistry()
    objects: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for object_id in sorted(grouped):
        try:
            objects.append(
                run_object(
                    object_id,
                    grouped[object_id],
                    out_dir,
                    pages_text=pages_text,
                    registry=registry,
                )
            )
        except (jsonschema.ValidationError, ValueError, OSError, QuarantineViolation) as exc:
            failures.append({"object_id": object_id, "reason": str(exc)})
    report: dict[str, object] = {
        "schema": RUN_SCHEMA,
        "closes_gate_i": False,
        "closes_gate_j": False,
        "closes_gate_k": False,
        "closes_gate_l": False,
        "mode": mode,
        "file_timeout_seconds": pdf_parse_timeout_s(),
        "versions": {
            "git_sha": git_sha(repo_root()),
            "matrix_version": registry.matrix_version,
            "dataset_version": os.environ.get("KONTUR_DATASET_VERSION", "").strip()
            or "unspecified",
            "model_version": os.environ.get("KONTUR_MODEL_VERSION", "").strip() or "none",
        },
        "objects": objects,
        "skipped": skipped,
        "stage_resolutions": resolutions,
        "failures": failures,
    }
    _write_json(out_dir / "run_manifest.json", report)
    return report


def _ensure_file_timeout() -> None:
    raw = os.environ.get("KONTUR_PDF_PARSE_TIMEOUT_S", "").strip()
    if not raw:
        os.environ["KONTUR_PDF_PARSE_TIMEOUT_S"] = str(int(FILE_TIMEOUT_S))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Пакетный прогон комплекта ПД/РД/ИД")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--pages-text",
        action="store_true",
        help="дополнительно pages_text_<obj>.jsonl: текст, bbox, engine",
    )
    args = parser.parse_args(argv)
    _ensure_file_timeout()
    try:
        report = run_directory(args.input, args.out, pages_text=args.pages_text)
    except (ValueError, OSError, QuarantineViolation) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    objects = report["objects"]
    skipped = report["skipped"]
    failures = report["failures"]
    if (
        not isinstance(objects, list)
        or not isinstance(skipped, list)
        or not isinstance(failures, list)
    ):
        raise TypeError("run_manifest")
    summary = {
        "objects": len(objects),
        "skipped": len(skipped),
        "failures": len(failures),
    }
    print(json.dumps(summary, ensure_ascii=False))
    if report["failures"] or not report["objects"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
