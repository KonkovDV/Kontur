"""Пакет сдачи #79: провенанс, coverage, два провода, без закрытия гейтов."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from kontur.application.protocol import assemble_protocol
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import (
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Extraction,
    ExtractionEngine,
    Finding,
)
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState, ReviewPriority
from kontur.evaluation.submission_pack import (
    COVERAGE_BUCKETS,
    PACK_SCHEMA,
    build_input_manifest,
    build_submission_pack,
    compose_container_inventory,
    load_gate_k,
    model_inventory,
)
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT, FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "contracts" / "schemas"
HASH = "a" * 64
SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))


def _completeness() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def _fragment() -> EvidenceFragment:
    return EvidenceFragment(
        fragment_id="frag-pd",
        role=EvidenceRole.EXPECTED,
        document=DocumentRef(
            file_id="file-pd",
            file_hash=HASH,
            doc_stage=DocStage.PD,
            document_code="12345-PD",
            revision="1",
            approval_status=ApprovalStatus.APPROVED,
            sheet="1",
        ),
        page=1,
        polygon_source=SQUARE,
        polygon_norm=SQUARE,
        extracted=Extraction(
            raw_token="1250,5",  # noqa: S106
            engine=ExtractionEngine.VECTOR,
            engine_version="pdfium",
            confidence=0.99,
            normalized_value="1250.5",
            grounded_in_source_tokens=True,
            second_read_agrees=True,
        ),
    )


def _group() -> EvidenceGroup:
    actual = EvidenceFragment(
        fragment_id="frag-rd",
        role=EvidenceRole.ACTUAL,
        document=DocumentRef(
            file_id="file-rd",
            file_hash="b" * 64,
            doc_stage=DocStage.RD,
            document_code="12345-RD",
            revision="1",
            approval_status=ApprovalStatus.APPROVED,
            sheet="1",
        ),
        page=1,
        polygon_source=SQUARE,
        polygon_norm=SQUARE,
        extracted=Extraction(
            raw_token="1100",  # noqa: S106
            engine=ExtractionEngine.VECTOR,
            engine_version="pdfium",
            confidence=0.9,
            normalized_value=1100.0,
            grounded_in_source_tokens=True,
        ),
    )
    return EvidenceGroup(
        evidence_group_id="eg-1",
        object_id="obj-pack",
        rule_code="PZ-001",
        matrix_version="draft-0",
        fragments=(_fragment(), actual),
    )


def _finding(status: FindingStatus) -> Finding:
    return Finding(
        finding_id="f-1",
        rule_code="PZ-001",
        finding_status=status,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id="eg-1",
        rationale="контроль",
    )


def _validate_pack(payload: dict[str, object]) -> None:
    resources: dict[str, Resource[dict[str, object]]] = {}
    for path in SCHEMAS.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(data)
        resources[str(data["$id"])] = resource
        resources[path.name] = resource
        resources[f"./{path.name}"] = resource

    def retrieve(uri: str) -> Resource[dict[str, object]]:
        try:
            return resources[uri]
        except KeyError as exc:
            raise LookupError(uri) from exc

    schema = json.loads((SCHEMAS / "submission_pack.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, registry=Registry(retrieve=retrieve)).validate(
        payload
    )


def _coverage_slice_of(report: dict[str, int]) -> dict[str, int]:
    """Ожидаемый срез: все вёдра покрытия плюс declared/expected_total."""

    slice_ = {name: int(report.get(name, 0)) for name in COVERAGE_BUCKETS}
    slice_["declared"] = int(report["declared"])
    slice_["expected_total"] = int(report["expected_total"])
    return slice_



def test_empty_pack_validates_and_keeps_gates_open() -> None:
    pack = build_submission_pack(root=REPO, environ={})
    _validate_pack(pack)
    assert pack["schema"] == PACK_SCHEMA
    assert pack["closes_gate_i"] is False
    assert pack["closes_gate_j"] is False
    assert pack["closes_gate_k"] is False
    assert pack["closes_gate_l"] is False
    coverage = pack["coverage"]
    assert coverage["declared"] == EXPECTED_PARAM_COUNT
    assert coverage == _coverage_slice_of(FileRuleRegistry().coverage_report())
    assert 20 <= coverage["executable"] < EXPECTED_PARAM_COUNT
    assert coverage["extractor_missing"] > 0
    assert sum(coverage[name] for name in COVERAGE_BUCKETS) == EXPECTED_PARAM_COUNT
    assert pack["protocol"] is None
    assert pack["submission"] is None
    assert pack["protocol_payload_sha256"] is None
    assert pack["models"] == []
    containers = pack["containers"]
    assert containers["digests_available"] is False
    names = {item["service"] for item in containers["services"]}
    assert {"postgres", "core", "outbox-relay", "gateway"} <= names
    gate = pack["gate_k"]
    assert gate["closes_gate_k"] is False
    assert gate["sessions_present"] is False
    assert "ocr_text_MEASURED_below_gate" in pack["limitations"]
    assert "GAP-IOS4-VAL" in pack["open_gaps"]
    assert pack["ci"]["run_id"] is None


def test_input_manifest_hash_is_stable() -> None:
    files = (
        {"file_id": "b", "file_hash": "b" * 64},
        {"file_id": "a", "file_hash": "a" * 64},
    )
    first = build_input_manifest(files)
    second = build_input_manifest(tuple(reversed(files)))
    assert first["manifest_hash"] == second["manifest_hash"]
    assert len(str(first["manifest_hash"])) == 64
    empty = build_input_manifest()
    assert empty["manifest_hash"] == "pending"


def test_model_hash_is_opt_in() -> None:
    assert model_inventory({}) == []
    digest = "c" * 64
    rows = model_inventory({"KONTUR_MODEL_SHA256": digest, "KONTUR_OCR_ENGINE": "tesseract"})
    assert rows == [{"name": "tesseract", "sha256": digest}]
    with pytest.raises(ValueError, match="SHA-256"):
        model_inventory({"KONTUR_MODEL_SHA256": "short"})


def test_compose_digest_comes_only_from_env() -> None:
    path = REPO / "docker-compose.yml"
    bare = compose_container_inventory(path, environ={})
    assert bare["digests_available"] is False
    tagged = compose_container_inventory(path, environ={"KONTUR_DIGEST_CORE": "sha256:abc"})
    core = next(item for item in tagged["services"] if item["service"] == "core")
    assert core["digest"] == "sha256:abc"
    assert tagged["digest_count"] == 1
    assert tagged["digests_available"] is False


def test_gate_k_raw_does_not_close_the_gate(tmp_path: Path) -> None:
    folder = tmp_path / "out" / "usability"
    folder.mkdir(parents=True)
    (folder / "session.json").write_text(
        json.dumps(
            {
                "schema_version": "kontur-usability-v1",
                "participant_id": "p-1",
                "closes_gate_k": True,
            }
        ),
        encoding="utf-8",
    )
    payload = load_gate_k(tmp_path)
    assert payload["sessions_present"] is True
    assert payload["session_count"] == 1
    assert payload["closes_gate_k"] is False
    raw = payload["raw"]
    assert isinstance(raw, list)
    assert raw[0]["closes_gate_k"] is False


def test_protocol_wire_drops_auto_no_difference() -> None:
    group = _group()
    equal = _finding(FindingStatus.AUTO_NO_DIFFERENCE)
    protocol = assemble_protocol(
        protocol_id="protocol-pack",
        object_id="obj-pack",
        findings=(equal,),
        completeness=_completeness(),
        files=[{"file_id": "file-pd", "file_hash": HASH}],
        versions={
            "matrix_version": "draft-0",
            "model_version": "none",
            "dataset_version": "unspecified",
            "git_sha": "unspecified",
        },
        process_state=ProcessState.COMPLETED,
        input_manifest_hash=HASH,
    )
    assert protocol["sections"]["preliminary_no_difference"]
    pack = build_submission_pack(
        object_id="obj-pack",
        findings=(equal,),
        groups=(group,),
        protocol=protocol,
        files=[{"file_id": "file-pd", "file_hash": HASH}],
        root=REPO,
        environ={},
    )
    _validate_pack(pack)
    wire = pack["protocol"]
    assert isinstance(wire, dict)
    sections = wire["sections"]
    assert isinstance(sections, dict)
    assert "preliminary_no_difference" not in sections
    assert "AUTO_NO_DIFFERENCE" not in json.dumps(wire)
    submission = pack["submission"]
    assert isinstance(submission, dict)
    checks = submission["checks"]
    assert isinstance(checks, list)
    assert checks[0]["violation_label"] == "NO_VIOLATION"
    digest = pack["protocol_payload_sha256"]
    assert isinstance(digest, str) and len(digest) == 64
    assert FindingStatus.CONFIRMED_VIOLATION.value not in json.dumps(pack)


def test_ci_url_is_built_from_github_env() -> None:
    pack = build_submission_pack(
        root=REPO,
        environ={
            "GITHUB_RUN_ID": "35578077145",
            "GITHUB_SHA": "cbce587",
            "GITHUB_REPOSITORY": "KonkovDV/Kontur",
            "GITHUB_SERVER_URL": "https://github.com",
        },
    )
    ci = pack["ci"]
    assert ci["run_id"] == "35578077145"
    assert ci["github_sha"] == "cbce587"
    assert ci["run_url"] == "https://github.com/KonkovDV/Kontur/actions/runs/35578077145"
