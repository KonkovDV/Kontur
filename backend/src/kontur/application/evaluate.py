"""Один проход правила: комплектность → извлечение → сравнение → находка.

Слайс исполняет:
  числовые  : extractor.type=number  + операторы из NUMERIC_OPERATORS
  обмер     : extractor.type=geometry + те же операторы (пара штрихов × масштаб)
  текстовые : extractor.type=enum    + операторы из STRING_OPERATORS | SET_OPERATORS
              extractor.type=text_regex + те же операторы

Человеческий вердикт сюда не пишется: максимум CANDIDATE или AUTO_NO_DIFFERENCE.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from uuid import uuid4

from kontur.application.comparators import (
    NUMERIC_OPERATORS,
    PRESENCE_OPERATORS,
    SET_OPERATORS,
    STRING_OPERATORS,
    Comparison,
    compare_values,
)
from kontur.application.extractors.geometry import extract_duct_width
from kontur.application.extractors.number import (
    NumberHit,
    PageToken,
    extract_number,
    parse_number_from_text,
)
from kontur.application.extractors.text import (
    TextHit,
    extract_exact_field,
    extract_presence,
    extract_text,
)
from kontur.application.pipeline import Stage, StageResult, run
from kontur.application.revision_resolver import (
    IdentityHead,
    ResolveStatus,
    RevisionConflict,
    resolve_heads_by_identity,
    resolve_revision,
)
from kontur.application.scenarios import CompletenessMap, status_for_missing_stage
from kontur.domain.coordinates import PageFrame
from kontur.domain.geometry import polygon_in_unit_square
from kontur.domain.idempotency import comparison_key
from kontur.domain.models import (
    ApprovalStatus,
    DocStage,
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    EvidenceRole,
    Finding,
)
from kontur.domain.statuses import (
    HUMAN_ONLY_STATUSES,
    Completeness,
    DisagreementKind,
    FindingStatus,
    ReviewPriority,
)
from kontur.infrastructure.ocr_tesseract import (
    PageImageCache,
    ocr_region_crop,
    tesseract_available,
)

_STAGE_ROLE: dict[DocStage, EvidenceRole] = {
    DocStage.PD: EvidenceRole.EXPECTED,
    DocStage.RD: EvidenceRole.ACTUAL,
    DocStage.ID: EvidenceRole.ACTUAL,
}

#: Типы экстракторов, работающих с текстом / enum-значениями.
_TEXT_EXTRACTOR_TYPES: frozenset[str] = frozenset({
    "enum",
    "text_regex",
    "exact_field",
    "presence",
})
_EXACT_FIELD_OPERATORS: frozenset[str] = frozenset({"eq", "ne"})
_TEXT_OPERATORS: frozenset[str] = STRING_OPERATORS | SET_OPERATORS | PRESENCE_OPERATORS

#: Покрытия, при которых автомат не имеет права публиковать CANDIDATE.
#: Экстрактор может работать, но заявленное покрытие говорит, что доказательство
#: неполное (advisory / доказательство вне пакета / параметр неприменим).
_NON_CANDIDATE_COVERAGE: frozenset[str] = frozenset({
    "advisory",
    "source_missing",
    "not_applicable",
})


@dataclass(frozen=True, slots=True)
class StagePage:
    document: DocumentRef
    tokens: tuple[PageToken, ...]
    pdf_bytes: bytes | None = None
    frames: tuple[PageFrame, ...] = ()
    render_cache: object | None = None


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


_KIND_LATIN: dict[str, str] = {
    "ПЗ": "PZ",
    "АР": "AR",
    "КР": "KR",
    "ИД": "ID",
    "ОВ": "OV",
    "КЖ": "KJ",
    "ОД": "OD",
    "ПЗУ": "PZU",
    "ИОС": "IOS",
    "ИОС4": "IOS4",
    "ПОС": "POS",
    "ПОД": "POD",
    "ЗУ": "ZU",
    "ППМ": "PPM",
    "ОДИ": "ODI",
    "ООС": "OOS",
    "СПЗУ": "SPZU",
}


def stage_candidates(
    pages: Mapping[DocStage, StagePage | Sequence[StagePage]],
    stage: DocStage,
) -> tuple[StagePage, ...]:
    raw = pages.get(stage)
    if raw is None:
        return ()
    if isinstance(raw, StagePage):
        return (raw,)
    return tuple(raw)


def _kind_aliases(raw: str) -> frozenset[str]:
    folded = raw.strip().upper().replace(" ", "")
    return frozenset({folded, _KIND_LATIN.get(folded, folded)})


def _wanted_kind_tokens(rule: dict[str, object], stage: DocStage) -> frozenset[str]:
    tokens: set[str] = set()
    section = rule.get("section")
    if isinstance(section, str) and section.strip():
        tokens.update(_kind_aliases(section))
    sources = rule.get("sources")
    if isinstance(sources, dict):
        bucket = sources.get(stage.value.lower())
        if isinstance(bucket, dict):
            kinds = bucket.get("document_kind")
            if isinstance(kinds, list):
                for item in kinds:
                    if isinstance(item, str) and item.strip():
                        tokens.update(_kind_aliases(item))
    return frozenset(tokens)


def _page_kind_tokens(page: StagePage) -> frozenset[str]:
    code = page.document.document_code.upper().replace("_", "-")
    parts = {code, *(item for item in code.split("-") if item)}
    if page.document.discipline:
        parts.add(page.document.discipline.upper())
    return frozenset(parts)


def _identity_kind_tokens(key: tuple[str, str, str]) -> frozenset[str]:
    code, _sheet, discipline = key
    folded = code.upper().replace("_", "-")
    parts = {folded, *(part for part in folded.split("-") if part)}
    if discipline:
        parts.add(discipline.upper())
    return frozenset(parts)


def _matching_identity_heads(
    identities: Sequence[IdentityHead],
    wanted: frozenset[str],
) -> tuple[IdentityHead, ...]:
    """Цепочки шифра, которые правило считает своим разделом. Пустой wanted — нет фильтра."""

    if not wanted:
        return ()
    return tuple(
        item
        for item in identities
        if item.key is not None and not wanted.isdisjoint(_identity_kind_tokens(item.key))
    )


def bind_stage_page(
    rule: dict[str, object],
    stage: DocStage,
    candidates: Sequence[StagePage],
) -> StagePage | str | None:
    """Одна голова раздела правила. Чужой шифр не даёт числа и не конфликтует."""

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    wanted = _wanted_kind_tokens(rule, stage)
    matched = [
        page
        for page in candidates
        if wanted and not wanted.isdisjoint(_page_kind_tokens(page))
    ]
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        ids = ", ".join(page.document.file_id for page in matched)
        return f"{stage.value}: несколько голов раздела правила ({ids})"
    ids = ", ".join(page.document.file_id for page in candidates)
    return f"{stage.value}: нет документа раздела правила среди голов {ids}"


def _bind_required_pages(
    rule: dict[str, object],
    pages: Mapping[DocStage, StagePage | Sequence[StagePage]],
    required: tuple[DocStage, ...],
) -> dict[DocStage, StagePage] | str:
    bound: dict[DocStage, StagePage] = {}
    for stage in required:
        picked = bind_stage_page(rule, stage, stage_candidates(pages, stage))
        if isinstance(picked, str):
            return picked
        if picked is not None:
            bound[stage] = picked
    for stage in pages:
        if stage in bound:
            continue
        extra = stage_candidates(pages, stage)
        if len(extra) == 1:
            bound[stage] = extra[0]
    return bound


def _assert_machine_status(status: FindingStatus) -> None:
    """Детерминизм: автомат не пишет человеческий вердикт (ADR-0001)."""

    if status in HUMAN_ONLY_STATUSES:
        raise RuntimeError(f"автомат не имеет права писать {status.value}")


def _quality_finding(
    rule: dict[str, object],
    status: FindingStatus,
    *,
    rationale: str,
) -> Finding:
    _assert_machine_status(status)
    kind = None
    if status is FindingStatus.MISSING_EVIDENCE:
        kind = DisagreementKind.MISSING_IN_STAGE
    return Finding(
        finding_id=str(uuid4()),
        rule_code=str(rule["code"]),
        finding_status=status,
        review_priority=_priority(rule),
        matrix_version=str(rule["matrix_version"]),
        rule_version="0.1.0",
        model_version="none",
        rationale=rationale,
        disagreement_kind=kind,
    )


def _downgrade_for_coverage(
    rule: dict[str, object], comparison: Comparison
) -> Comparison:
    """CANDIDATE запрещён для advisory / source_missing / not_applicable.

    Правило с таким покрытием честно объявляет, что доказательство неполное:
    сравнение остаётся в находке (expected/actual/delta/evidence_refs), но
    статус понижается до low_quality и расхождение уходит инспектору.
    """

    if comparison.status is not FindingStatus.CANDIDATE:
        return comparison
    coverage = str(rule.get("coverage") or "")
    if coverage not in _NON_CANDIDATE_COVERAGE:
        return comparison
    return replace(
        comparison,
        status=_mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
        rationale=(
            f"{comparison.rationale}; coverage={coverage}: "
            "расхождение не публикуется как кандидат, решает инспектор"
        ),
    )


def _finding_from_comparison(
    rule: dict[str, object],
    comparison: Comparison,
    *,
    group_id: str,
    fragments: tuple[EvidenceFragment, ...],
    pages: dict[DocStage, StagePage],
) -> Finding:
    comparison = _downgrade_for_coverage(rule, comparison)
    _assert_machine_status(comparison.status)
    pd = pages.get(DocStage.PD)
    source_id = pd.document.file_id if pd is not None else fragments[0].document.file_id
    kind = None
    if comparison.status is FindingStatus.CANDIDATE:
        kind = DisagreementKind.VALUE_DELTA
    return Finding(
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
        source_id=source_id,
        evidence_refs=tuple(item.fragment_id for item in fragments),
        disagreement_kind=kind,
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


def _localize(hit: NumberHit | TextHit) -> bool:
    return hit.page >= 1 and polygon_in_unit_square(hit.polygon_norm)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"ожидалось число, получено {value!r}")
    return float(value)


def _fragment(
    hit: NumberHit | TextHit,
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


def _dual_read_required(rule: dict[str, object]) -> bool:
    """Читаем флаг extractor.dual_read_required; по умолчанию True."""
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return True
    dr = extractor.get("dual_read_required")
    return dr is not False


def _ocr_region_agrees(hit: NumberHit, page: StagePage, rule: dict[str, object]) -> bool | None:
    """Независимый region-crop. None — верификатор не запускался, не disagreement."""

    if page.pdf_bytes is None or not page.frames:
        return None
    if not tesseract_available():
        return None
    if hit.page < 1 or hit.page > len(page.frames):
        return None
    frame = page.frames[hit.page - 1]
    cache = page.render_cache if isinstance(page.render_cache, PageImageCache) else None
    tokens = ocr_region_crop(
        page.pdf_bytes,
        page_number=hit.page,
        frame=frame,
        polygon=hit.polygon_source,
        cache=cache,
    )
    if not tokens:
        return None
    value = parse_number_from_text(" ".join(item.text for item in tokens), rule)
    if value is None:
        return None
    try:
        primary = _as_float(hit.extraction.normalized_value)
    except TypeError:
        return None
    return primary == value


def evaluate_rule(
    rule: dict[str, object],
    *,
    object_id: str,
    pages: Mapping[DocStage, StagePage | Sequence[StagePage]],
    completeness: CompletenessMap,
    revision_pool: list[DocumentRef] | None = None,
    inspector_selected_file_ids: frozenset[str] = frozenset(),
) -> RuleEvaluation:
    """Исполнить одно правило на уже разрезанных страницах."""

    extractor = rule.get("extractor")
    comparator = rule.get("comparator")
    extractor_type = extractor.get("type") if isinstance(extractor, dict) else None
    operator = comparator.get("operator") if isinstance(comparator, dict) else None
    is_text = extractor_type in _TEXT_EXTRACTOR_TYPES
    if extractor_type == "exact_field":
        valid_operators = _EXACT_FIELD_OPERATORS
    else:
        valid_operators = _TEXT_OPERATORS if is_text else NUMERIC_OPERATORS

    if extractor_type not in ("number", "geometry", *_TEXT_EXTRACTOR_TYPES):
        return _halt(
            rule,
            Stage.L6_MATRIX,
            FindingStatus.CLARIFICATION_REQUIRED,
            "слайс исполняет extractor.type=number/geometry/enum/text_regex/exact_field/presence, "
            f"получено {extractor_type!r}",
        )
    if not isinstance(comparator, dict) or operator not in valid_operators:
        return _halt(
            rule,
            Stage.L6_MATRIX,
            FindingStatus.CLARIFICATION_REQUIRED,
            f"слайс исполняет операторы {sorted(valid_operators)!r}, "
            f"получен {operator!r}",
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

    revision_status = _mapped(rule, "revision_conflict", FindingStatus.CLARIFICATION_REQUIRED)
    if revision_pool is not None:
        for stage in required:
            wanted = _wanted_kind_tokens(rule, stage)
            matched = _matching_identity_heads(
                resolve_heads_by_identity(
                    revision_pool,
                    stage,
                    inspector_selected_file_ids=inspector_selected_file_ids,
                ),
                wanted,
            )
            if len(matched) != 1:
                continue
            identity = matched[0]
            if (
                identity.resolution.status is not ResolveStatus.RESOLVED
                or identity.resolution.resolved is None
            ):
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    revision_status,
                    identity.resolution.conflict_reason
                    or f"{stage.value}: эталон не выбран",
                    prior=identity_ok,
                )
    bound = _bind_required_pages(rule, pages, required)
    if isinstance(bound, str):
        return _halt(
            rule,
            Stage.L4_REVISION,
            revision_status,
            bound,
            prior=identity_ok,
        )
    pages = bound

    for stage, page in pages.items():
        if not _identity_ok(page):
            return _halt(
                rule,
                Stage.L1_IDENTITY,
                FindingStatus.CLARIFICATION_REQUIRED,
                f"{stage.value}: нет file_id/SHA-256 или страница 0",
            )

    if revision_pool is not None:
        for stage in required:
            try:
                staged = pages.get(stage)
                resolution = resolve_revision(
                    revision_pool,
                    stage,
                    anchor=None if staged is None else staged.document,
                    inspector_selected_file_ids=inspector_selected_file_ids,
                )
            except RevisionConflict as exc:
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    revision_status,
                    str(exc),
                    prior=identity_ok,
                )
            if resolution.status is ResolveStatus.MISSING_EVIDENCE:
                mapped = _mapped(rule, "source_absent", FindingStatus.MISSING_EVIDENCE)
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    mapped,
                    resolution.conflict_reason or f"{stage.value}: нет документов стадии",
                    prior=identity_ok,
                    missing_stage=stage,
                )
            if resolution.status is not ResolveStatus.RESOLVED or resolution.resolved is None:
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    revision_status,
                    resolution.conflict_reason or f"{stage.value}: эталон не выбран",
                    prior=identity_ok,
                )
            current = pages.get(stage)
            chosen = resolution.resolved.document
            if current is None or current.document.file_id != chosen.file_id:
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    revision_status,
                    (
                        f"{stage.value}: страница не последняя утверждённая редакция"
                        f" ({chosen.file_id})"
                    ),
                    prior=identity_ok,
                )
    else:
        for stage, page in pages.items():
            approval = page.document.approval_status
            if approval is ApprovalStatus.NOT_APPROVED:
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    revision_status,
                    f"{stage.value}: редакция помечена «не утв.»",
                    prior=identity_ok,
                )
            if stage is DocStage.PD and approval is not ApprovalStatus.APPROVED:
                return _halt(
                    rule,
                    Stage.L4_REVISION,
                    revision_status,
                    f"{stage.value}: эталон без признака утверждения",
                    prior=identity_ok,
                )

    dual_req = _dual_read_required(rule)

    # ── ветка текстового / enum экстрактора ───────────────────────────────────
    if is_text:
        text_hits: dict[DocStage, TextHit] = {}
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
            if extractor_type == "exact_field":
                hit = extract_exact_field(stage_page.tokens, rule)
            elif extractor_type == "presence":
                hit = extract_presence(stage_page.tokens, rule)
            else:
                hit = extract_text(stage_page.tokens, rule)
            if hit is None:
                return _halt(
                    rule,
                    Stage.L2_EXTRACTION,
                    _mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
                    f"{stage.value}: якорь или значение не найдены",
                    prior=identity_ok,
                )
            if dual_req and hit.extraction.second_read_agrees is not True:
                return _halt(
                    rule,
                    Stage.L2_EXTRACTION,
                    _mapped(rule, "reads_disagree", FindingStatus.ABSTAIN),
                    f"{stage.value}: два чтения текста не совпали",
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
            text_hits[stage] = hit

        if DocStage.PD not in text_hits or DocStage.RD not in text_hits:
            return _halt(
                rule,
                Stage.L5_PAIRING,
                _mapped(rule, "not_comparable", FindingStatus.NOT_COMPARABLE),
                "для текстового оператора нужны ПД и РД",
                prior=(
                    *identity_ok,
                    StageResult(Stage.L2_EXTRACTION, ok=True),
                    StageResult(Stage.L3_LOCALIZATION, ok=True),
                    StageResult(Stage.L4_REVISION, ok=True),
                ),
            )

        text_stages = (
            StageResult(Stage.L1_IDENTITY, ok=True),
            StageResult(Stage.L2_EXTRACTION, ok=True),
            StageResult(Stage.L3_LOCALIZATION, ok=True),
            StageResult(Stage.L4_REVISION, ok=True),
            StageResult(Stage.L5_PAIRING, ok=True),
            StageResult(Stage.L6_MATRIX, ok=True),
            StageResult(Stage.L7_FINDINGS, ok=True),
        )
        if run(list(text_stages)) is not None:
            raise RuntimeError("каскад L1-L7 закрылся до сравнения (text-path)")

        comparison = compare_values(
            text_hits[DocStage.PD].extraction.normalized_value,
            text_hits[DocStage.RD].extraction.normalized_value,
            rule,
        )
        file_ids = tuple(pages[stage].document.file_id for stage in text_hits)
        group_id = comparison_key(object_id, str(rule["code"]), file_ids)
        _assert_machine_status(comparison.status)
        text_fragments = tuple(
            _fragment(
                hit,
                role=_STAGE_ROLE[stage],
                document=pages[stage].document,
                fragment_id=f"{group_id}-{stage.value}",
            )
            for stage, hit in text_hits.items()
        )
        text_group = EvidenceGroup(
            evidence_group_id=group_id,
            object_id=object_id,
            rule_code=str(rule["code"]),
            matrix_version=str(rule["matrix_version"]),
            fragments=text_fragments,
            resolved_revisions=tuple(pages[stage].document for stage in text_hits),
        )
        text_finding = _finding_from_comparison(
            rule,
            comparison,
            group_id=group_id,
            fragments=text_fragments,
            pages=pages,
        )
        return RuleEvaluation(
            finding=text_finding, evidence_group=text_group, stages=text_stages
        )

    # ── ветка числового экстрактора (оригинальная логика) ────────────────────
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
        if extractor_type == "geometry":
            number_hit, detail = extract_duct_width(
                stage_page.tokens,
                stage_page.pdf_bytes,
                stage_page.frames,
                rule,
            )
            missing = detail
        else:
            number_hit = extract_number(stage_page.tokens, rule)
            missing = "якорь или число не найдены"
        if number_hit is None:
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
                f"{stage.value}: {missing}",
                prior=identity_ok,
            )
        if dual_req and number_hit.extraction.second_read_agrees is not True:
            disagree = (
                "два чтения сечения не совпали"
                if extractor_type == "geometry"
                else "два чтения числа не совпали"
            )
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "reads_disagree", FindingStatus.ABSTAIN),
                f"{stage.value}: {disagree}",
                prior=identity_ok,
            )
        if (
            extractor_type != "geometry"
            and dual_req
            and _ocr_region_agrees(number_hit, stage_page, rule) is False
        ):
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "reads_disagree", FindingStatus.ABSTAIN),
                f"{stage.value}: vector и OCR region-crop не совпали",
                prior=identity_ok,
            )
        if not number_hit.extraction.usable_for_automatic_finding:
            return _halt(
                rule,
                Stage.L2_EXTRACTION,
                _mapped(rule, "low_quality", FindingStatus.LOW_QUALITY),
                f"{stage.value}: значение не grounded",
                prior=identity_ok,
            )
        if not _localize(number_hit):
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
        hits[stage] = number_hit

    if DocStage.PD not in hits or DocStage.RD not in hits:
        return _halt(
            rule,
            Stage.L5_PAIRING,
            _mapped(rule, "not_comparable", FindingStatus.NOT_COMPARABLE),
            "для числового оператора нужны ПД и РД",
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
        raise RuntimeError("каскад L1-L7 закрылся до сравнения")

    file_ids = tuple(pages[stage].document.file_id for stage in hits)
    group_id = comparison_key(object_id, str(rule["code"]), file_ids)
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
    finding = _finding_from_comparison(
        rule,
        comparison,
        group_id=group_id,
        fragments=fragments,
        pages=pages,
    )
    return RuleEvaluation(finding=finding, evidence_group=group, stages=stages)

