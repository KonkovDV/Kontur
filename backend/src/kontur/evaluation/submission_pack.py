"""Пакет сдачи: провенанс + JSON участника. Не закрывает гейты I/J/K/L."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from kontur.application.protocol import canonical_protocol_json, protocol_for_http
from kontur.domain.models import EvidenceGroup, Finding
from kontur.evaluation.agent_dumps import build_handoff, git_sha, repo_root
from kontur.evaluation.submission import findings_to_submission
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry

PACK_SCHEMA = "kontur.submission_pack.v1"
_HEX = frozenset("0123456789abcdef")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_input_manifest(files: Sequence[Mapping[str, str]] = ()) -> dict[str, object]:
    """Канонический манифест входа. Пустой комплект — pending, не выдуманный хеш."""

    normalized: list[dict[str, str]] = []
    for item in files:
        file_id = str(item["file_id"]).strip()
        file_hash = str(item["file_hash"]).strip().lower()
        if not file_id:
            raise ValueError("input_manifest: пустой file_id")
        if len(file_hash) != 64 or any(char not in _HEX for char in file_hash):
            raise ValueError(f"input_manifest: {file_id} без SHA-256")
        normalized.append({"file_id": file_id, "file_hash": file_hash})
    normalized.sort(key=lambda row: (row["file_id"], row["file_hash"]))
    if not normalized:
        return {"manifest_hash": "pending", "files": []}
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"manifest_hash": _sha256_text(encoded), "files": normalized}


def compose_container_inventory(
    compose_path: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Сервисы Compose. Digest только из env, не выдумывается."""

    env = os.environ if environ is None else environ
    raw = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("docker-compose.yml: не объект")
    services = raw.get("services")
    if not isinstance(services, dict):
        raise ValueError("docker-compose.yml: нет services")
    rows: list[dict[str, object]] = []
    digest_count = 0
    for name, spec in services.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            continue
        row: dict[str, object] = {"service": name}
        image = spec.get("image")
        if isinstance(image, str) and image.strip():
            row["image"] = image.strip()
        build = spec.get("build")
        if isinstance(build, str) and build.strip():
            row["build"] = build.strip()
        elif isinstance(build, dict):
            dockerfile = build.get("dockerfile")
            context = build.get("context")
            if isinstance(dockerfile, str) and dockerfile.strip():
                row["dockerfile"] = dockerfile.strip()
            if isinstance(context, str) and context.strip():
                row["context"] = context.strip()
        key = "KONTUR_DIGEST_" + name.upper().replace("-", "_")
        digest = str(env.get(key, "")).strip()
        if digest:
            row["digest"] = digest
            digest_count += 1
        rows.append(row)
    return {
        "digests_available": bool(rows) and digest_count == len(rows),
        "digest_count": digest_count,
        "service_count": len(rows),
        "services": rows,
    }


def model_inventory(environ: Mapping[str, str] | None = None) -> list[dict[str, str]]:
    """Хеши моделей только если задан KONTUR_MODEL_SHA256. Пустой список — честно."""

    env = os.environ if environ is None else environ
    digest = str(env.get("KONTUR_MODEL_SHA256", "")).strip().lower()
    if not digest:
        return []
    if len(digest) != 64 or any(char not in _HEX for char in digest):
        raise ValueError("KONTUR_MODEL_SHA256 должен быть hex SHA-256")
    engine = str(env.get("KONTUR_OCR_ENGINE", "")).strip() or "unnamed_model"
    return [{"name": engine, "sha256": digest}]


def ci_run_from_env(environ: Mapping[str, str] | None = None) -> dict[str, str | None]:
    env = os.environ if environ is None else environ
    run_id = str(env.get("GITHUB_RUN_ID", "")).strip() or None
    sha = str(env.get("GITHUB_SHA", "")).strip() or None
    repo = str(env.get("GITHUB_REPOSITORY", "")).strip() or None
    server = str(env.get("GITHUB_SERVER_URL", "https://github.com")).rstrip("/")
    url = f"{server}/{repo}/actions/runs/{run_id}" if run_id and repo else None
    return {"run_id": run_id, "run_url": url, "github_sha": sha}


def load_gate_k(root: Path) -> dict[str, object]:
    """Сырые JSON рекордера, если лежат в out/usability. Гейт K кодом не закрывается."""

    folder = root / "out" / "usability"
    raw: list[dict[str, object]] = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("schema_version") != "kontur-usability-v1":
                continue
            payload["closes_gate_k"] = False
            raw.append(payload)
    return {
        "closes_gate_k": False,
        "sessions_present": bool(raw),
        "session_count": len(raw),
        "raw": raw,
        "note": (
            "пять сессий в USABILITY_RESULTS.md закрывают гейт; "
            "сырой JSON рекордера этого не делает"
        ),
    }


# Разбивка покрытия шире пары executable/extractor_missing: правило может быть
# advisory, source_missing или not_applicable. Сумма всех вёдер обязана дать 132.
COVERAGE_BUCKETS: tuple[str, ...] = (
    "executable",
    "extractor_missing",
    "advisory",
    "source_missing",
    "not_applicable",
)


def _as_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(name)
    return value


def _coverage_slice(counts: Mapping[str, object]) -> dict[str, int]:
    buckets = {name: _as_int(counts.get(name, 0), name) for name in COVERAGE_BUCKETS}
    declared = _as_int(counts["declared"], "declared")
    expected = _as_int(counts["expected_total"], "expected_total")
    if declared != EXPECTED_PARAM_COUNT or expected != EXPECTED_PARAM_COUNT:
        raise ValueError(f"матрица {declared}/{expected}, ожидалось {EXPECTED_PARAM_COUNT}")
    if buckets["executable"] >= EXPECTED_PARAM_COUNT:
        raise ValueError("нельзя заявить всю матрицу executable")
    if sum(buckets.values()) != EXPECTED_PARAM_COUNT:
        raise ValueError("разбивка coverage не сходится к 132")
    return {**buckets, "declared": declared, "expected_total": expected}


def build_submission_pack(
    *,
    object_id: str | None = None,
    findings: Sequence[Finding] = (),
    groups: Sequence[EvidenceGroup] = (),
    protocol: Mapping[str, object] | None = None,
    files: Sequence[Mapping[str, str]] = (),
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Собрать пакет. AUTO_NO_DIFFERENCE на провод протокола не попадает."""

    base = root or repo_root()
    env = os.environ if environ is None else environ
    registry = FileRuleRegistry()
    handoff = build_handoff(root=base)
    counts = handoff["coverage_counts"]
    if not isinstance(counts, dict):
        raise TypeError("coverage_counts")
    limitations = handoff["pipeline_limitations"]
    gaps = handoff["open_gaps"]
    if not isinstance(limitations, list) or not isinstance(gaps, list):
        raise TypeError("limitations/open_gaps")

    wire_protocol = protocol_for_http(protocol) if protocol is not None else None
    protocol_digest = None
    if wire_protocol is not None:
        protocol_digest = _sha256_text(canonical_protocol_json(wire_protocol))

    submission: dict[str, object] | None = None
    if findings:
        if object_id is None or not object_id.strip():
            raise ValueError("submission pack с находками требует object_id")
        codes = registry.all_codes()
        rules = {code: registry.get(code) for code in codes}
        submission = findings_to_submission(
            object_id,
            findings,
            groups,
            known_codes=codes,
            rules=rules,
        )

    return {
        "schema": PACK_SCHEMA,
        "generated_on": date.today().isoformat(),
        "closes_gate_i": False,
        "closes_gate_j": False,
        "closes_gate_k": False,
        "closes_gate_l": False,
        "versions": {
            "git_sha": git_sha(base),
            "matrix_version": registry.matrix_version,
            "dataset_version": str(env.get("KONTUR_DATASET_VERSION", "")).strip()
            or "unspecified",
            "model_version": str(env.get("KONTUR_MODEL_VERSION", "")).strip() or "none",
        },
        "coverage": _coverage_slice(counts),
        "input_manifest": build_input_manifest(files),
        "containers": compose_container_inventory(
            base / "docker-compose.yml", environ=env
        ),
        "models": model_inventory(env),
        "ci": ci_run_from_env(env),
        "limitations": list(limitations),
        "open_gaps": list(gaps),
        "gate_k": load_gate_k(base),
        "protocol": wire_protocol,
        "submission": submission,
        "protocol_payload_sha256": protocol_digest,
    }
