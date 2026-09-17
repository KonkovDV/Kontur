"""Gate K — ProtocolReport Engine.

SOTA:
  Evidence-based XAI for construction (Zhang et al., 2026) §4.2
  HCAI DSS Review (Cai et al., 2026) — ≤3 clicks/finding
  BLUEPRINT (Liang et al., 2026) — blueprint-aware evidence linking
  ExtractConf (ACL 2025) — calibrated confidence
TZ: Appendix 2, tables 1-5; scoring §9.4
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    BLOCKER  = "BLOCKER"
    CRITICAL = "CRITICAL"
    MAJOR    = "MAJOR"
    MINOR    = "MINOR"
    INFO     = "INFO"


class FindingStatus(str, Enum):
    CONFIRMED_VIOLATION = "CONFIRMED_VIOLATION"
    ABSTAINED           = "ABSTAINED"
    COMPLIANT           = "COMPLIANT"


class OcrPath(str, Enum):
    VECTOR_PDFIUM = "VECTOR_PDFIUM"
    RASTER_REGION = "RASTER_REGION"
    HYBRID        = "HYBRID"


# ---------------------------------------------------------------------------
# Scoring constants (TZ §9.4)
# ---------------------------------------------------------------------------

SEVERITY_PENALTY: Dict[Severity, float] = {
    Severity.BLOCKER:  10.0,
    Severity.CRITICAL:  7.0,
    Severity.MAJOR:     5.0,
    Severity.MINOR:     2.0,
    Severity.INFO:      0.0,
}

# Gate K core constraint (HCAI DSS Review 2026)
MAX_CLICKS = 3

# CA threshold (Gate I — Risk-Controlled Generative OCR 2026)
CA_GATE_I_THRESHOLD = 0.97


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoundingBox:
    """Normalised [0,1]×[0,1] bbox on a PDF page."""
    page: int    # 1-indexed
    x0:   float
    y0:   float
    x1:   float
    y1:   float

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError(f"BoundingBox.page must be ≥1, got {self.page}")
        for name, lo, hi in [("x0", 0.0, 1.0), ("y0", 0.0, 1.0),
                              ("x1", 0.0, 1.0), ("y1", 0.0, 1.0)]:
            v = getattr(self, name)
            if not (lo <= v <= hi):
                raise ValueError(
                    f"BoundingBox.{name} must be in [0,1], got {v}"
                )
        if self.x0 >= self.x1:
            raise ValueError(
                f"BoundingBox: x0={self.x0} must be < x1={self.x1}"
            )
        if self.y0 >= self.y1:
            raise ValueError(
                f"BoundingBox: y0={self.y0} must be < y1={self.y1}"
            )

    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


@dataclass(frozen=True)
class EvidenceSnippet:
    """OCR-extracted text fragment tied to a BoundingBox."""
    text:               str
    bbox:               BoundingBox
    confidence:         float   # ExtractConf weighted geometric mean
    character_accuracy: float   # CA = 1 − CER ∈ [0,1]
    ocr_path:           OcrPath

    def __post_init__(self) -> None:
        for name in ("confidence", "character_accuracy"):
            v = getattr(self, name)
            if not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"EvidenceSnippet.{name} must be in [0,1], got {v}"
                )

    def meets_ca_gate(self) -> bool:
        return self.character_accuracy >= CA_GATE_I_THRESHOLD


@dataclass
class EvidenceCard:
    """Gate K evidence unit — one finding with full audit trail.

    Gate K constraint (HCAI DSS Review 2026):
      clicks_to_navigate <= MAX_CLICKS (3)
    All 132 catalog parameters must be reachable in <=3 clicks.
    """
    rule_code:          str
    severity:           Severity
    status:             FindingStatus
    extracted_value:    Optional[str]
    expected_value:     Optional[str]
    snippets:           List[EvidenceSnippet] = field(default_factory=list)
    clicks_to_navigate: int = 1
    rule_description:   str = ""
    norm_ref:           str = ""

    def __post_init__(self) -> None:
        if self.clicks_to_navigate > MAX_CLICKS:
            raise ValueError(
                f"Gate K: clicks_to_navigate={self.clicks_to_navigate} > {MAX_CLICKS}. "
                "All findings must be reachable in <=3 clicks (HCAI DSS Review 2026)."
            )
        if self.clicks_to_navigate < 1:
            raise ValueError(
                f"clicks_to_navigate must be >=1, got {self.clicks_to_navigate}"
            )

    @property
    def penalty(self) -> float:
        if self.status == FindingStatus.CONFIRMED_VIOLATION:
            return SEVERITY_PENALTY[self.severity]
        return 0.0

    @property
    def is_blocker(self) -> bool:
        return (
            self.status == FindingStatus.CONFIRMED_VIOLATION
            and self.severity == Severity.BLOCKER
        )


@dataclass
class DocumentMetadata:
    doc_id:                str
    model_version:         str
    run_timestamp_utc:     float = field(default_factory=time.time)
    calibration_threshold: float = 0.75
    ocr_primary:           str   = OcrPath.VECTOR_PDFIUM.value
    ocr_verifier:          str   = OcrPath.RASTER_REGION.value


@dataclass
class ProtocolReport:
    """Appendix 2 — all 5 mandatory output tables."""
    metadata:    DocumentMetadata
    cards:       List[EvidenceCard]     = field(default_factory=list)
    risk_matrix: List[Dict[str, Any]]  = field(default_factory=list)

    @property
    def total_penalty(self) -> float:
        return sum(c.penalty for c in self.cards)

    @property
    def overall_passed(self) -> bool:
        return not any(c.is_blocker for c in self.cards)

    @property
    def violation_count(self) -> int:
        return sum(
            1 for c in self.cards
            if c.status == FindingStatus.CONFIRMED_VIOLATION
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "doc_id":                  self.metadata.doc_id,
                "model_version":           self.metadata.model_version,
                "run_timestamp_utc":       self.metadata.run_timestamp_utc,
                "calibration_threshold":   self.metadata.calibration_threshold,
                "ocr_primary":             self.metadata.ocr_primary,
                "ocr_verifier":            self.metadata.ocr_verifier,
            },
            "summary": {
                "overall_passed":   self.overall_passed,
                "total_penalty":    self.total_penalty,
                "violation_count":  self.violation_count,
                "card_count":       len(self.cards),
            },
            "violations": [
                {
                    "rule_code":        c.rule_code,
                    "severity":         c.severity.value,
                    "status":           c.status.value,
                    "extracted_value":  c.extracted_value,
                    "expected_value":   c.expected_value,
                    "penalty":          c.penalty,
                    "norm_ref":         c.norm_ref,
                    "rule_description": c.rule_description,
                    "clicks_to_navigate": c.clicks_to_navigate,
                    "snippets": [
                        {
                            "text":               s.text,
                            "confidence":         s.confidence,
                            "character_accuracy": s.character_accuracy,
                            "ocr_path":           s.ocr_path.value,
                            "meets_ca":           s.meets_ca_gate(),
                            "bbox": {
                                "page": s.bbox.page,
                                "x0":   s.bbox.x0,
                                "y0":   s.bbox.y0,
                                "x1":   s.bbox.x1,
                                "y1":   s.bbox.y1,
                            },
                        }
                        for s in c.snippets
                    ],
                }
                for c in self.cards
            ],
            "risk_matrix": self.risk_matrix,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_pdf_bytes(self) -> bytes:
        """Minimal valid PDF stub.
        Production: replace with WeasyPrint/ReportLab rendering.
        """
        return (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n0 4\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"trailer<</Size 4/Root 1 0 R>>\n"
            b"startxref\n190\n%%EOF\n"
        )


class ProtocolReportBuilder:
    """Fluent builder for ProtocolReport."""

    def __init__(self, doc_id: str, model_version: str = "kontur-v1") -> None:
        self._meta  = DocumentMetadata(doc_id=doc_id, model_version=model_version)
        self._cards: List[EvidenceCard]    = []
        self._risk:  List[Dict[str, Any]]  = list(DEFAULT_RISK_MATRIX)

    def add_card(self, card: EvidenceCard) -> "ProtocolReportBuilder":
        self._cards.append(card)
        return self

    def with_risk_matrix(
        self, matrix: List[Dict[str, Any]]
    ) -> "ProtocolReportBuilder":
        self._risk = list(matrix)
        return self

    def build(self) -> ProtocolReport:
        return ProtocolReport(
            metadata=self._meta,
            cards=list(self._cards),
            risk_matrix=list(self._risk),
        )


# ---------------------------------------------------------------------------
# Default risk matrix (representative sample; full catalog in jsonl)
# ---------------------------------------------------------------------------

DEFAULT_RISK_MATRIX: List[Dict[str, Any]] = [
    {"rule_code": "PZ-001",  "severity": Severity.BLOCKER.value,  "penalty": 10.0, "group": "PZ",   "description": "Печать/штамп"},
    {"rule_code": "PZ-002",  "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "PZ",   "description": "Общая площадь"},
    {"rule_code": "PZ-003",  "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "PZ",   "description": "Масштаб чертежа"},
    {"rule_code": "PZ-004",  "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "PZ",   "description": "Стр. объем (общ.)"},
    {"rule_code": "PZ-005",  "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "PZ",   "description": "Стр. объем (подз.)"},
    {"rule_code": "PZ-006",  "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "PZ",   "description": "Этажность надз."},
    {"rule_code": "PZ-007",  "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "PZ",   "description": "Этажность подз."},
    {"rule_code": "PZ-008",  "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "PZ",   "description": "Высота здания"},
    {"rule_code": "PZ-009",  "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "PZ",   "description": "Абс. отм. 0.000"},
    {"rule_code": "PZ-010",  "severity": Severity.MINOR.value,    "penalty":  2.0, "group": "PZ",   "description": "Кол. квартир"},
    {"rule_code": "SPZU-024","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "SPZU", "description": "Объем грунта"},
    {"rule_code": "SPZU-025","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "SPZU", "description": "Площадь участка"},
    {"rule_code": "AR-040",  "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "AR",   "description": "Назначение здания"},
    {"rule_code": "AR-041",  "severity": Severity.BLOCKER.value,  "penalty": 10.0, "group": "AR",   "description": "Ширина эвак. двери ≥0.9м"},
    {"rule_code": "KR-054",  "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "KR",   "description": "Класс бетона (фунд.)"},
    {"rule_code": "KR-055",  "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "KR",   "description": "Класс бетона (несущ.)"},
    {"rule_code": "IOS1-068","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "IOS1", "description": "Водоснабжение"},
    {"rule_code": "IOS2-071","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "IOS2", "description": "Канализация"},
    {"rule_code": "IOS3-074","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "IOS3", "description": "Отопление"},
    {"rule_code": "IOS4-076","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "IOS4", "description": "Вентиляция"},
    {"rule_code": "IOS5-080","severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "IOS5", "description": "Электроснабжение"},
    {"rule_code": "POS-081", "severity": Severity.MAJOR.value,    "penalty":  5.0, "group": "POS",  "description": "Срок стр-ва"},
    {"rule_code": "POS-082", "severity": Severity.MINOR.value,    "penalty":  2.0, "group": "POS",  "description": "Трудозатраты"},
    {"rule_code": "POD-090", "severity": Severity.BLOCKER.value,  "penalty": 10.0, "group": "POD",  "description": "Номер проекта"},
    {"rule_code": "OOS-098", "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "OOS",  "description": "Сметная стоимость"},
    {"rule_code": "PPM-102", "severity": Severity.BLOCKER.value,  "penalty": 10.0, "group": "PPM",  "description": "Категория пожарн. опасн."},
    {"rule_code": "ODI-115", "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "ODI",  "description": "Доступность МГН"},
    {"rule_code": "ZU-124",  "severity": Severity.BLOCKER.value,  "penalty": 10.0, "group": "ZU",   "description": "Вид разр. использования"},
    {"rule_code": "SM-132",  "severity": Severity.CRITICAL.value, "penalty":  7.0, "group": "SM",   "description": "Сметный расчёт итог"},
]
