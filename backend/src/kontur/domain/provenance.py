"""Finding provenance types (donor: AeroBIM source_id + evidence_refs pattern).

Gate K requirement: inspector must reach the source in ≤3 clicks.
Every auto-generated finding SHOULD carry a source_id that references the
exact PDF location or IFC element where the value was extracted.

DisagreementKind mirrors AeroBIM ConflictKind taxonomy.
Kontur variant covers document-vs-document disagreements from the 132-parameter
matrix (reads_disagree → DisagreementKind-typed, not just ABSTAIN).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kontur.domain.models import DocStage, EvidenceRole, Polygon


class DisagreementKind(StrEnum):
    """Why two source reads disagree (donor: AeroBIM ConflictKind taxonomy).

    VALUE_DELTA          — numeric values differ beyond ε (e.g. 600×300 vs 400×250)
    MISSING_IN_STAGE     — value present in one stage, absent in another
    AMBIGUOUS_REFERENCE  — same code maps to multiple values in one document
    FORMAT_MISMATCH      — same physical quantity in different units/formats
    """

    VALUE_DELTA = "value_delta"
    MISSING_IN_STAGE = "missing_in_stage"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"
    FORMAT_MISMATCH = "format_mismatch"


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Exact location of a value inside a PDF page (Gate K ≤3-click provenance).

    fragment_id links back to EvidenceFragment in the EvidenceGroup.
    polygon_source is the bounding box of the raw token on the page.
    """

    fragment_id: str
    doc_stage: DocStage
    page: int                     # 1-indexed
    polygon_source: Polygon       # bounding box on the page
    locator_hint: str | None = None  # human-readable: section title, table row

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be ≥ 1 (1-indexed)")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Light reference to one EvidenceFragment inside a Finding.

    Allows the UI to jump directly to the fragment without loading the full
    EvidenceGroup — supports the ≤3-click Gate K requirement.
    """

    fragment_id: str
    role: EvidenceRole
    doc_stage: DocStage
    page: int                     # 1-indexed
    locator_hint: str | None = None

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be ≥ 1 (1-indexed)")
