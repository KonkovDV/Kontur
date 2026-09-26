"""Карточка доказательства: схема, сериализация, учебные JSON. Не Gate K."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from kontur.application.evidence_card import (
    SCHEMA_VERSION,
    build_evidence_card,
    evidence_group_to_schema,
)
from kontur.application.runtime import ProcessWorkspace
from kontur.domain.geometry import bbox_from_polygon
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
from kontur.domain.statuses import Completeness, DisagreementKind, FindingStatus, ReviewPriority

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "contracts" / "schemas"
DEMO_CARDS = REPO / "web" / "src" / "demo_cards.json"
HASH_PD = "a" * 64
HASH_RD = "b" * 64


def _registry() -> Registry[str]:
    registry: Registry[str] = Registry()
    for path in SCHEMAS.glob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents)
        ident = str(contents.get("$id") or path.name)
        registry = registry.with_resource(ident, resource)
    return registry


def _validator() -> Draft202012Validator:
    schema = json.loads((SCHEMAS / "evidence_card.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=_registry())


def _doc(stage: DocStage, file_id: str, digest: str) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=digest,
        doc_stage=stage,
        document_code=f"DOC-{stage.value}",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
    )


def _fragment(
    role: EvidenceRole,
    stage: DocStage,
    digest: str,
    raw: str,
    value: float,
) -> EvidenceFragment:
    polygon = ((0.1, 0.2), (0.4, 0.2), (0.4, 0.3), (0.1, 0.3))
    return EvidenceFragment(
        fragment_id=f"eg-1-{stage.value}",
        role=role,
        document=_doc(stage, f"file-{stage.value.lower()}", digest),
        page=1,
        polygon_source=((72.0, 400.0), (200.0, 400.0), (200.0, 430.0), (72.0, 430.0)),
        polygon_norm=polygon,
        extracted=Extraction(
            raw_token=raw,
            engine=ExtractionEngine.VECTOR,
            engine_version="pdfium",
            confidence=0.9,
            normalized_value=value,
            unit="м²",
            grounded_in_source_tokens=True,
            second_read_agrees=True,
        ),
    )


def _group() -> EvidenceGroup:
    return EvidenceGroup(
        evidence_group_id="eg-1",
        object_id="obj-1",
        rule_code="PZ-001",
        matrix_version="draft-0",
        fragments=(
            _fragment(EvidenceRole.EXPECTED, DocStage.PD, HASH_PD, "1250,5", 1250.5),
            _fragment(EvidenceRole.ACTUAL, DocStage.RD, HASH_RD, "1100", 1100.0),
        ),
        resolved_revisions=(
            _doc(DocStage.PD, "file-pd", HASH_PD),
            _doc(DocStage.RD, "file-rd", HASH_RD),
        ),
    )


def _candidate() -> Finding:
    return Finding(
        finding_id="f-1",
        evidence_group_id="eg-1",
        rule_code="PZ-001",
        finding_status=FindingStatus.CANDIDATE,
        review_priority=ReviewPriority.HIGH,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        expected_value=1250.5,
        actual_value=1100.0,
        delta=-150.5,
        source_id="file-pd",
        evidence_refs=("eg-1-PD", "eg-1-RD"),
        disagreement_kind=DisagreementKind.VALUE_DELTA,
        rationale="delta вне допуска",
    )


def test_card_matches_schema_and_keeps_raw() -> None:
    group = _group()
    card = build_evidence_card(
        process_id="p-1",
        finding=_candidate(),
        group=group,
        rule={
            "code": "PZ-001",
            "name": "Площадь застройки",
            "unit": "м²",
            "comparator": {
                "operator": "delta",
                "tolerance_abs": 0.0,
                "tolerance_rel": None,
                "rounding": "half_up",
                "unit_target": "м²",
            },
        },
        audit_records=(
            ("insp-7", "REVIEW", {"finding_id": "f-1", "action": "CONFIRM"}),
            ("insp-7", "SELECT_REVISION", {"file_id": "file-pd"}),
            ("system", "PIPELINE", {"rules_evaluated": 132}),
        ),
    )
    _validator().validate(card)
    assert card["schema_version"] == SCHEMA_VERSION
    assert card["closes_gate_k"] is False
    group_payload = card["evidence_group"]
    assert isinstance(group_payload, dict)
    expected = group_payload["fragments"][0]["extracted"]
    assert expected["raw_token"] == "1250,5"  # noqa: S105
    assert expected["normalized_value"] == 1250.5
    polygon = tuple(tuple(point) for point in group_payload["fragments"][0]["polygon_norm"])
    bbox = bbox_from_polygon(polygon)
    assert bbox == (0.1, 0.2, 0.4, 0.3)
    actions = [event["action"] for event in card["audit"]]
    assert actions == ["REVIEW", "SELECT_REVISION"]
    assert card["finding"]["finding_status"] == "CANDIDATE"
    assert card["finding"]["counts_as_violation"] is False


def test_missing_evidence_card_has_null_group() -> None:
    finding = Finding(
        finding_id="f-miss",
        rule_code="IOS4-079",
        finding_status=FindingStatus.MISSING_EVIDENCE,
        review_priority=ReviewPriority.MEDIUM,
        matrix_version="draft-0",
        rule_version="0.1.0",
        model_version="none",
        rationale="нет ИД",
    )
    card = build_evidence_card(
        process_id="p-1",
        finding=finding,
        group=None,
        rule={"code": "IOS4-079"},
        audit_records=(),
    )
    _validator().validate(card)
    assert card["evidence_group"] is None
    assert card["closes_gate_k"] is False


def test_group_id_mismatch_fails_closed() -> None:
    finding = _candidate()
    other = EvidenceGroup(
        evidence_group_id="eg-other",
        object_id="obj-1",
        rule_code="PZ-001",
        matrix_version="draft-0",
        fragments=_group().fragments,
    )
    with pytest.raises(ValueError, match="расходится"):
        build_evidence_card(
            process_id="p-1",
            finding=finding,
            group=other,
            rule={"code": "PZ-001"},
            audit_records=(),
        )


def test_fragment_rejects_a_short_hash_and_a_norm_outside_the_square() -> None:
    document = _doc(DocStage.PD, "file-pd", "abc")
    sample = _fragment(EvidenceRole.EXPECTED, DocStage.PD, HASH_PD, "1", 1.0)
    with pytest.raises(ValueError, match="SHA-256"):
        EvidenceFragment(
            fragment_id=sample.fragment_id,
            role=sample.role,
            document=document,
            page=1,
            polygon_source=sample.polygon_source,
            polygon_norm=sample.polygon_norm,
            extracted=sample.extracted,
        )
    with pytest.raises(ValueError, match="polygon_norm"):
        EvidenceFragment(
            fragment_id=sample.fragment_id,
            role=sample.role,
            document=sample.document,
            page=1,
            polygon_source=sample.polygon_source,
            polygon_norm=((0.1, 0.2), (1.2, 0.2), (1.2, 0.4), (0.1, 0.4)),
            extracted=sample.extracted,
        )


def test_group_rejects_a_single_role() -> None:
    with pytest.raises(ValueError, match="expected и actual"):
        EvidenceGroup(
            evidence_group_id="eg-one",
            object_id="obj-1",
            rule_code="PZ-001",
            matrix_version="draft-0",
            fragments=(_fragment(EvidenceRole.EXPECTED, DocStage.PD, HASH_PD, "1", 1.0),),
        )


def test_demo_cards_validate_and_do_not_close_gate_k() -> None:
    cards = json.loads(DEMO_CARDS.read_text(encoding="utf-8"))
    assert isinstance(cards, list)
    assert len(cards) == 5
    validator = _validator()
    statuses = []
    for card in cards:
        validator.validate(card)
        assert card["closes_gate_k"] is False
        statuses.append(card["finding"]["finding_status"])
    assert statuses.count("MISSING_EVIDENCE") == 1
    assert statuses.count("CANDIDATE") == 4
    assert "CONFIRMED_VIOLATION" not in statuses


def test_pipeline_keeps_groups_on_the_process_record() -> None:
    workspace = ProcessWorkspace()
    record = workspace.create(
        "obj-groups",
        {
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.MISSING,
            DocStage.ID: Completeness.MISSING,
        },
    )
    workspace.put_finding(record.process_id, _candidate())
    record.evidence_groups[_group().evidence_group_id] = _group()
    stored = workspace.get(record.process_id)
    assert stored is not None
    group = stored.evidence_groups["eg-1"]
    payload = evidence_group_to_schema(group)
    assert payload["fragments"][0]["document"]["file_hash"] == HASH_PD
    assert len(payload["fragments"][0]["document"]["file_hash"]) == 64
