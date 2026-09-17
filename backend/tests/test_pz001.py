"""Вертикальный слайс PZ-001: якорь → число → delta → evidence → review → протокол."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.application.protocol import assemble_protocol, finding_to_schema
from kontur.application.review import review
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.domain.state_machines import Actor
from kontur.domain.status_map import on_the_wire
from kontur.domain.statuses import Completeness, FindingStatus, ProcessState
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
SCHEMAS = REPO / "contracts" / "schemas"
HASH = "a" * 64
OBJECT_ID = "OBJ-TYUMENSKAYA-5-GOLD-SEED"


@pytest.fixture(scope="module")
def rule() -> dict[str, object]:
    registry = FileRuleRegistry(REPO / "data" / "matrix")
    payload = registry.get("PZ-001")
    assert payload["coverage"] == "executable"
    return payload


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    width, height = 0.10, 0.04
    polygon = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _line(*values: str) -> tuple[PageToken, ...]:
    return tuple(_tok(text, 0.08 + index * 0.14) for index, text in enumerate(values))


def _document(stage: DocStage, *, approved: bool = True) -> DocumentRef:
    return DocumentRef(
        file_id=f"file-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code=f"12345-{stage.value}-TEP",
        revision="2",
        approval_status=ApprovalStatus.APPROVED if approved else ApprovalStatus.UNKNOWN,
        sheet="ОД",
    )


def _page(stage: DocStage, *cells: str, approved: bool = True) -> StagePage:
    return StagePage(document=_document(stage, approved=approved), tokens=_line(*cells))


def _completeness(*, rd: Completeness = Completeness.UPLOADED) -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: rd,
        DocStage.ID: Completeness.MISSING,
    }


def _run(
    rule: dict[str, object],
    pd: tuple[str, ...],
    rd: tuple[str, ...] | None,
    *,
    rd_state: Completeness = Completeness.UPLOADED,
    approved: bool = True,
):
    pages = {DocStage.PD: _page(DocStage.PD, *pd, approved=approved)}
    if rd is not None:
        pages[DocStage.RD] = _page(DocStage.RD, *rd, approved=approved)
    return evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness(rd=rd_state),
    )


def test_pz001_is_executable() -> None:
    """Гейт G: PZ-001 был первым правилом, помеченным executable.

    Примечание: гейт H добавляет больше executable правил; этот тест
    проверяет только PZ-001, не весь список.
    Полный перечень проверяется в test_gate_h_e2e.py::test_executable_count.
    """
    registry = FileRuleRegistry(REPO / "data" / "matrix")
    assert registry.get("PZ-001")["coverage"] == "executable", "PZ-001 должен оставаться executable"


def test_equal_values_give_no_difference(rule: dict[str, object]) -> None:
    result = _run(
        rule,
        ("Площадь", "застройки", "1 250,50"),
        ("Площадь", "застройки", "1250,5"),
    )
    finding = result.finding
    assert finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
    assert finding.evidence_group_id is not None
    assert result.evidence_group is not None
    assert finding.delta == 0.0
    assert finding.finding_status not in {
        FindingStatus.CANDIDATE,
        FindingStatus.CONFIRMED_VIOLATION,
    }


def test_missing_value_is_quality_not_human_verdict(rule: dict[str, object]) -> None:
    """Параметр не найден в загруженном документе — не нарушение и не NEGATIVE_VERIFIED."""

    result = _run(
        rule,
        ("Площадь", "застройки"),
        ("Площадь", "застройки", "1250,5"),
    )
    assert result.finding.finding_status is FindingStatus.LOW_QUALITY
    assert result.finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert result.finding.finding_status is not FindingStatus.NEGATIVE_VERIFIED
    assert result.finding.evidence_group_id is None


def test_evidence_group_id_is_stable_across_retries(rule: dict[str, object]) -> None:
    first = _run(
        rule,
        ("Площадь", "застройки", "1 250,50"),
        ("Площадь", "застройки", "1250,5"),
    )
    second = _run(
        rule,
        ("Площадь", "застройки", "1 250,50"),
        ("Площадь", "застройки", "1250,5"),
    )
    assert first.evidence_group is not None
    assert second.evidence_group is not None
    assert first.evidence_group.evidence_group_id == second.evidence_group.evidence_group_id


def test_any_difference_gives_candidate(rule: dict[str, object]) -> None:
    result = _run(
        rule,
        ("Площадь", "застройки", "1250,5"),
        ("Площадь", "застройки", "1100"),
    )
    finding = result.finding
    assert finding.finding_status is FindingStatus.CANDIDATE
    assert finding.finding_status is not FindingStatus.CONFIRMED_VIOLATION
    assert finding.evidence_group_id is not None
    assert result.evidence_group is not None
    assert finding.expected_value == 1250.5
    assert finding.actual_value == 1100.0
    for fragment in result.evidence_group.fragments:
        assert fragment.page >= 1
        assert fragment.document.file_hash == HASH
        assert fragment.extracted.grounded_in_source_tokens
        assert fragment.extracted.second_read_agrees is True


def test_rd_absent_gives_missing_evidence(rule: dict[str, object]) -> None:
    result = _run(
        rule,
        ("Площадь", "застройки", "1250,5"),
        None,
        rd_state=Completeness.MISSING,
    )
    assert result.finding.finding_status is FindingStatus.MISSING_EVIDENCE
    assert result.finding.evidence_group_id is None
    assert result.missing_stage is DocStage.RD
    assert result.finding.finding_status is not FindingStatus.CANDIDATE


def test_ocr_reads_disagree_gives_abstain(rule: dict[str, object]) -> None:
    result = _run(
        rule,
        ("Площадь", "застройки", "1250,5", "1100"),
        ("Площадь", "застройки", "1250,5"),
    )
    assert result.finding.finding_status is FindingStatus.ABSTAIN
    assert result.finding.evidence_group_id is None


def test_unapproved_revision_does_not_compare(rule: dict[str, object]) -> None:
    result = _run(
        rule,
        ("Площадь", "застройки", "1250,5"),
        ("Площадь", "застройки", "1100"),
        approved=False,
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.finding_status is not FindingStatus.CANDIDATE


def test_pool_rejects_page_that_is_not_approved_head(rule: dict[str, object]) -> None:
    """RT-2709-08 в слайсе: в страницах черновик, в пуле есть утверждённый предшественник."""

    draft = _document(DocStage.PD, approved=False)
    head = DocumentRef(
        file_id="file-pd-approved",
        file_hash=HASH,
        doc_stage=DocStage.PD,
        document_code="12345-PD-TEP",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
        successor_file_id=draft.file_id,
    )
    rd = _document(DocStage.RD)
    pages = {
        DocStage.PD: StagePage(document=draft, tokens=_line("Площадь", "застройки", "1250,5")),
        DocStage.RD: StagePage(document=rd, tokens=_line("Площадь", "застройки", "1100")),
    }
    result = evaluate_rule(
        rule,
        object_id=OBJECT_ID,
        pages=pages,
        completeness=_completeness(),
        revision_pool=[head, draft, rd],
    )
    assert result.finding.finding_status is FindingStatus.CLARIFICATION_REQUIRED
    assert result.finding.evidence_group_id is None


def test_review_and_protocol_close_the_slice(rule: dict[str, object]) -> None:
    result = _run(
        rule,
        ("Площадь", "застройки", "1250,5"),
        ("Площадь", "застройки", "1100"),
    )
    actor = Actor(actor_id="insp-7", is_human=True)
    confirmed = review(
        result.finding,
        actor=actor,
        action="CONFIRM",
        comment="расхождение ТЭП ПД и листа общих данных РД",
    )
    assert confirmed.finding_status is FindingStatus.CONFIRMED_VIOLATION
    assert confirmed.counts_as_violation

    equal = _run(
        rule,
        ("Площадь", "застройки", "1250,5"),
        ("Площадь", "застройки", "1250,5"),
    )
    protocol = assemble_protocol(
        protocol_id="proto-pz001",
        object_id=OBJECT_ID,
        findings=(confirmed, equal.finding),
        completeness=_completeness(),
        files=[
            {"file_id": "file-pd", "file_hash": HASH},
            {"file_id": "file-rd", "file_hash": HASH},
        ],
        versions={
            "matrix_version": "draft-0",
            "model_version": "none",
            "dataset_version": "unspecified",
        },
        process_state=ProcessState.COMPLETED,
        input_manifest_hash=HASH,
    )
    sections = protocol["sections"]
    assert protocol["status"] == "VERIFICATION_COMPLETED"
    assert protocol["violation_count"] == 1
    assert protocol["violation_count"] == len(sections["confirmed"])
    assert sections["confirmed"][0]["counts_as_violation"] is True
    assert sections["preliminary_no_difference"][0]["finding_status"] == "AUTO_NO_DIFFERENCE"
    assert not any(
        card["finding_status"] == "AUTO_NO_DIFFERENCE"
        for card in [
            *sections["candidates"],
            *sections["confirmed"],
            *sections["negative_verified"],
        ]
    )
    assert on_the_wire(FindingStatus.AUTO_NO_DIFFERENCE) is False
    _validate_protocol(protocol)
    jsonschema.validate(finding_to_schema(confirmed), _finding_schema())


def _finding_schema() -> dict[str, object]:
    return json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))


def _validate_protocol(payload: dict[str, object]) -> None:
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

    schema = json.loads((SCHEMAS / "protocol.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, registry=Registry(retrieve=retrieve)).validate(
        payload
    )
