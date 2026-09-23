"""Доменные сущности. Зеркалят contracts/schemas — схема первична."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from kontur.domain.statuses import (
    STATUSES_REQUIRING_EVIDENCE,
    DisagreementKind,
    FindingStatus,
    ReasonCode,
    ReviewPriority,
)

Point = tuple[float, float]
Polygon = tuple[Point, ...]


class DocStage(StrEnum):
    PD = "PD"
    RD = "RD"
    ID = "ID"


class ApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    NOT_APPROVED = "NOT_APPROVED"
    UNKNOWN = "UNKNOWN"


class ApprovalBasis(StrEnum):
    """Откуда взялся approval_status. Не источник вердикта о нарушении."""

    TITLE_BLOCK = "TITLE_BLOCK"
    INSPECTOR_SELECT = "INSPECTOR_SELECT"
    UNPROVEN = "UNPROVEN"


class EvidenceRole(StrEnum):
    EXPECTED = "expected"
    ACTUAL = "actual"
    CONTEXT = "context"


class ExtractionEngine(StrEnum):
    VECTOR = "vector"
    OCR = "ocr"
    VLM = "vlm"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class DocumentRef:
    file_id: str
    file_hash: str
    doc_stage: DocStage
    document_code: str
    revision: str
    approval_status: ApprovalStatus
    approval_basis: ApprovalBasis = ApprovalBasis.UNPROVEN
    discipline: str | None = None
    approval_date: date | None = None
    sheet: str | None = None
    predecessor_file_id: str | None = None
    successor_file_id: str | None = None


@dataclass(frozen=True, slots=True)
class Extraction:
    """Извлечённое значение.

    raw_token хранится дословно и никогда не перезаписывается нормализацией.
    grounded_in_source_tokens=False запрещает автоматическую находку: значение
    не подтверждено ни векторным слоем, ни OCR-токенами страницы (ADR-0001).
    """

    raw_token: str
    engine: ExtractionEngine
    engine_version: str
    confidence: float
    normalized_value: str | float | bool | None = None
    unit: str | None = None
    grounded_in_source_tokens: bool = False
    second_read_agrees: bool | None = None
    confidence_features: dict[str, float] = field(default_factory=dict)

    @property
    def usable_for_automatic_finding(self) -> bool:
        """Значение годится для автоматического сравнения."""

        if not self.grounded_in_source_tokens:
            return False
        return self.second_read_agrees is not False


@dataclass(frozen=True, slots=True)
class EvidenceFragment:
    fragment_id: str
    role: EvidenceRole
    document: DocumentRef
    page: int
    polygon_source: Polygon
    polygon_norm: Polygon
    extracted: Extraction

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("номер страницы начинается с 1, а не с 0")


@dataclass(frozen=True, slots=True)
class EvidenceGroup:
    """Единица результата и разметки (ADR-0002)."""

    evidence_group_id: str
    object_id: str
    rule_code: str
    matrix_version: str
    fragments: tuple[EvidenceFragment, ...]
    resolved_revisions: tuple[DocumentRef, ...] = ()

    def role(self, role: EvidenceRole) -> EvidenceFragment | None:
        return next((f for f in self.fragments if f.role is role), None)


@dataclass(frozen=True, slots=True)
class InspectorDecision:
    inspector_id: str
    action: str
    timestamp: datetime
    reason_code: ReasonCode | None = None
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    """Атомарная находка.

    Составной кандидат не существует: он дробится на атомарные находки, каждая
    со своим доказательством и своим решением (ТЗ п. 9.3).
    """

    finding_id: str
    rule_code: str
    finding_status: FindingStatus
    review_priority: ReviewPriority
    matrix_version: str
    rule_version: str
    model_version: str
    evidence_group_id: str | None = None
    expected_value: str | float | bool | None = None
    actual_value: str | float | bool | None = None
    delta: str | float | None = None
    rationale: str = ""
    llm_draft: str | None = None
    inspector_decision: InspectorDecision | None = None
    source_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    disagreement_kind: DisagreementKind | None = None

    def __post_init__(self) -> None:
        if self.finding_status in STATUSES_REQUIRING_EVIDENCE and not self.evidence_group_id:
            raise ValueError(f"{self.finding_status} requires evidence_group_id")
        if self.finding_status is FindingStatus.CONFIRMED_VIOLATION:
            decision = self.inspector_decision
            if decision is None or decision.action != "CONFIRM":
                raise ValueError("CONFIRMED_VIOLATION requires inspector CONFIRM")
            if not decision.comment or not decision.comment.strip():
                raise ValueError("CONFIRMED_VIOLATION requires comment")
        if self.finding_status is FindingStatus.NEGATIVE_VERIFIED:
            decision = self.inspector_decision
            if decision is None or decision.action != "REJECT":
                raise ValueError("NEGATIVE_VERIFIED requires inspector REJECT")
            if decision.reason_code is None:
                raise ValueError("NEGATIVE_VERIFIED requires reason_code")
            if not decision.comment or not decision.comment.strip():
                raise ValueError("NEGATIVE_VERIFIED requires comment")

    @property
    def counts_as_violation(self) -> bool:
        return (
            self.finding_status is FindingStatus.CONFIRMED_VIOLATION
            and self.inspector_decision is not None
        )

    @property
    def has_provenance(self) -> bool:
        """Предметная находка с группой доказательств и file_id эталона."""

        return bool(self.evidence_group_id) and bool(self.source_id)
