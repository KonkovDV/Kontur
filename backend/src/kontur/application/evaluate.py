"""Один проход правила: комплектность → извлечение → сравнение → находка.

Слайз исполняет `extractor.type=number` и `comparator.operator=delta`.
Другой оператор — отказ L6, а не «почти delta». Человеческий вердикт сюда
не пишется: максимум CANDIDATE или AUTO_NO_DIFFERENCE.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from kontur.application.comparators import compare_values
from kontur.application.extractors.number import NumberHit, PageToken, extract_number
from kontur.application.pipeline import Stage, StageResult, run
from kontur.application.scenarios import CompletenessMap, status_for_missing_stage
from kontur.domain.geometry import polygon_in_unit_square
from kontur.domain.models import (
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Finding,
)
from kontur.domain.statuses import Completeness, FindingStatus, ReviewPriority

_STAGE_ROLE: dict[DocStage, EvidenceRole] = {
    DocStage.PD: EvidenceRole.EXPECTED,
    DocStage.RD: EvidenceRole.ACTUAL,
    DocStage.ID: EvidenceRole.ACTUAL,
}


@dataclass(frozen=True, slots=True)
class StagePage:
    document: DocumentRef
    tokens: tuple[PageToken, ...]


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    finding: Finding
    evidence_group: EvidenceGroup | None
    stages: tuple[StageResult, ...]
    missing_stage: DocStage | None = None


def _mapped(rule: dict[str, object], key: str, default: FindingStatus) -> FindingStatus:
    mapping = rule.get("failure_mapping")
    if not isinstance(mapping, dict):
        return default
    raw = mapping.get(key)
    if not isinstance(raw, str):
        return default
    return FindingStatus(raw)


def _priority(rule: dict[str, object]) -> ReviewPriority:
    raw = rule.get("review_priority")
    if raw in {item.value for item in ReviewPriority}:
        return ReviewPriority(str(raw))
    return ReviewPriority.HIGH


def _required_stages(rule: dict[str, object]) -> tuple[DocStage, ...]:
    applicability = rule.get("applicability")
    if not isinstance(applicability, dict):
        return (DocStage.PD, DocStage.RD)
    raw = applicability.get("stages_required")
    if not isinstance(raw, list) or not raw:
        return (DocStage.PD, DocStage.RD)
    return tuple(DocStage(str(item)) for item in raw)


def _quality_finding(
    rule: dict[str, object],
    status: FindingStatus,
    *,
    rationale: str,
) -> Finding:
    return Finding(
        finding_id=str(uuid4()),
        rule_code=str(rule["code"]),
        finding_status=status,
        review_priority=_priority(rule),
        matrix_version=str(rule["matrix_version"]),
        rule_version="0.1.0",
        model_version="none",
        rationale=rationale,
    )


def _halt(
    rule: dict[str, object],
    stage: Stage,
    status: FindingStatus,
    detail: str,
    *,
    prior: tuple[StageResult, ...] = (),
    missing_stage: DocStage | None = None,
) -> RuleEvaluation:
    stages = (*prior, StageResult(stage, ok=False, status=status, detail=detail))
    halted = run(list(stages))
    if halted is not status:
        raise RuntimeError(f"каскад вернул {halted}, ожидалось {status}")
    return RuleEvaluation(
        finding=_quality_finding(rule, status, rationale=detail),
        evidence_group=None,
        stages=stages,
        missing_stage=missing_stage,
    )


def _identity_ok(page: StagePage) -> bool:
    document = page.document
    if not document.file_id.strip():
        return False
    if len(document.file_hash) != 64:
        return False
    return all(token.page >= 1 for token in page.tokens)


def _localize(hit: NumberHit) -> bool:
    return hit.page >= 1 and polygon_in_unit_square(hit.polygon_norm)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"ожидалось число, получено {value!r}")
    return float(value)


def _fragment(
    hit: NumberHit,
    *,
    role: EvidenceRole,
    document: DocumentRef,
    fragment_id: str,
) -> EvidenceFragment:
    return EvidenceFragment(
        fragment_id=fragment_id,
        role=role,
        document=document,
        page=hit.page,
        polygon_source=hit.polygon_source,
        polygon_norm=hit.polygon_norm,
        extracted=hit.extraction,
    )


def evaluate_rule(
    rule: dict[str, object],
    *,
    object_id: str,
    pages: dict[DocStage, StagePage],
    completeness: CompletenessMap,
) -> RuleEvaluation:
    """Исполнить одно правило на уже разрезанных страницах."""

    extractor = rule.get("extractor")
    comparator = rule.get("comparator")
    if not isinstance(extractor, dict) or extractor.get("type") != "number":
        return _halt(
            rule,
            Stage.L6_MATRIX,
            FindingStatus.CLARIFICATION_REQUIRED,
            "слайс исполняет только extractor.type=number",
        )
    if not isinstance(comparator, dict) or comparator.get("operator") != "delta":
        return _halt(
            rule,
            Stage.L6_MATRIX,
            FindingStatus.CLARIFICATION_REQUIRED,
            "слайс исполняет только comparator.operator=delta",
        )

    required = _required_stages(rule)
    identity_ok = (StageResult(Stage.L1_IDENTITY, ok=True),)
    for stage in required:
        state = completeness.get(stage, Completeness.MISSING)
        if state is Completeness.MISSING:
            status = status_for_missing_stage(
                stage_required_by_rule=True, stage_applicable_to_object=True
            )
            mapped = _mapped(rule, "source_absent", status)
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                mapped,
                f"{stage.value} не представлен, сравнение не запускалось",
                prior=identity_ok,
                missing_stage=stage,
            )

    for stage, page in pages.items():
        if not _identity_ok(page):
            return _halt(
                rule,
                Stage.L1_IDENTITY,
                FindingStatus.CLARIFICATION_REQUIRED,
                f"{stage.value}: нет file_id/SHA-256 или страница 0",
            )
        if page.document.approval_status is not ApprovalStatus.APPROVED:
            return _halt(
                rule,
                Stage.L4_REVISION,
                _mapped(rule, "revision_conflict", FindingStatus.CLARIFICATION_REQUIRED),
                f"{stage.value}: эталон без признака утверждения",
                prior=identity_ok,
            )

    hits: dict[DocStage, NumberHit] = {}
    for stage in required:
        stage_page = pages.get(stage)
        if stage_page is None:
            mapped = _mapped(rule, "source_absent", FindingStatus.MISSING_EVIDENCE)
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                mapped,
                f"{stage.value}: страница не передана",
                prior=identity_ok,
                missing_stage=stage,
            )
        hit = extract_number(stage_page.tokens, rule)
        if hit is None:
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
                f"{stage.value}: якорь или число не найдены",
                prior=identity_ok,
            )
        if hit.extraction.second_read_agrees is not True:
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "reads_disagree", FindingStatus.ABSTAIN),
                f"{stage.value}: два чтения числа не совпали",
                prior=identity_ok,
            )
        if not hit.extraction.usable_for_automatic_finding:
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
                f"{stage.value}: значение не grounded",
                prior=identity_ok,
            )
        if not _localize(hit):
            return _halt(
                rule,
                Stage.L3_LOCALIZATION,
                _mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
                f"{stage.value}: polygon_norm вне [0;1] или страница < 1",
                prior=(
                    *identity_ok,
                    StageResult(Stage.L2_EXTRACTION, ok=True),
                ),
            )
        hits[stage] = hit

    if DocStage.PD not in hits or DocStage.RD not in hits:
        return _halt(
            rule,
            Stage.L5_PAIRING,
            _mapped(rule, "not_comparable", FindingStatus.NOT_COMPARABLE),
            "для delta нужны ПД и РД",
            prior=(
                *identity_ok,
                StageResult(Stage.L2_EXTRACTION, ok=True),
                StageResult(Stage.L3_LOCALIZATION, ok=True),
                StageResult(Stage.L4_REVISION, ok=True),
            ),
        )

    comparison = compare_values(
        _as_float(hits[DocStage.PD].extraction.normalized_value),
        _as_float(hits[DocStage.RD].extraction.normalized_value),
        rule,
    )
    stages = (
        StageResult(Stage.L1_IDENTITY, ok=True),
        StageResult(Stage.L2_EXTRACTION, ok=True),
        StageResult(Stage.L3_LOCALIZATION, ok=True),
        StageResult(Stage.L4_REVISION, ok=True),
        StageResult(Stage.L5_PAIRING, ok=True),
        StageResult(Stage.L6_MATRIX, ok=True),
        StageResult(Stage.L7_FINDINGS, ok=True),
    )
    if run(list(stages)) is not None:
        raise RuntimeError("каскад L1–L7 закрылся до сравнения")

    group_id = str(uuid4())
    fragments = tuple(
        _fragment(
            hit,
            role=_STAGE_ROLE[stage],
            document=pages[stage].document,
            fragment_id=f"{group_id}-{stage.value}",
        )
        for stage, hit in hits.items()
    )
    group = EvidenceGroup(
        evidence_group_id=group_id,
        object_id=object_id,
        rule_code=str(rule["code"]),
        matrix_version=str(rule["matrix_version"]),
        fragments=fragments,
        resolved_revisions=tuple(pages[stage].document for stage in hits),
    )
    finding = Finding(
        finding_id=str(uuid4()),
        rule_code=str(rule["code"]),
        finding_status=comparison.status,
        review_priority=_priority(rule),
        matrix_version=str(rule["matrix_version"]),
        rule_version="0.1.0",
        model_version="none",
        evidence_group_id=group_id,
        expected_value=comparison.expected,
        actual_value=comparison.actual,
        delta=comparison.delta,
        rationale=comparison.rationale,
    )
    return RuleEvaluation(finding=finding, evidence_group=group, stages=stages)
