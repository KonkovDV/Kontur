"""Protocol export adapter — Appendix 2 format (Gate K).

Формат протокола согласно Приложению 2 ТЗ (Г2 v1.1).

Структура протокола:
  - Заголовок: объект, адрес, дата, сценарий
  - Раздел 1: Отклонения (нарушения) — CANDIDATE + MISSING_EVIDENCE
  - Раздел 2: Автоматические совпадения — AUTO_NO_DIFFERENCE
  - Раздел 3: Требуют проверки вручную — ABSTAIN, CLARIFICATION_REQUIRED, LOW_QUALITY
  - Раздел 4: Неприменимы — NOT_APPLICABLE
  - Раздел 5: Свободные находки (free-search findings)
  - Подпись: подпись, дата, проверяющий организм

AUTO_NO_DIFFERENCE не сериализируется в протокол как нарушение,
но попадает в Раздел 2 (автоматические совпадения).

Вопрос 8 (ТЗ v1.1): формат раздела по ответу организатора остаётся открытым —
пока используем подход «один раздел = одна категория».

Refs: ТЗ Приложение 2, Gate K (26.09), PLAN_2026_09.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class FindingStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    AUTO_NO_DIFFERENCE = "AUTO_NO_DIFFERENCE"
    ABSTAIN = "ABSTAIN"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    LOW_QUALITY = "LOW_QUALITY"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    FREE_SEARCH = "FREE_SEARCH"


_SECTION_DEVIATIONS = frozenset({
    FindingStatus.CANDIDATE,
    FindingStatus.MISSING_EVIDENCE,
})
_SECTION_AUTO = frozenset({FindingStatus.AUTO_NO_DIFFERENCE})
_SECTION_MANUAL = frozenset({
    FindingStatus.ABSTAIN,
    FindingStatus.CLARIFICATION_REQUIRED,
    FindingStatus.LOW_QUALITY,
    FindingStatus.NOT_COMPARABLE,
})
_SECTION_NA = frozenset({FindingStatus.NOT_APPLICABLE})


@dataclass
class ProtocolFinding:
    parameter_code: str  # e.g. "PZ-001"
    parameter_name: str
    status: FindingStatus
    section_ref: str | None = None  # " НП 1.1.1", норм. ссылка
    pd_value: str | None = None  # значение в ПД
    rd_value: str | None = None  # значение в РД
    id_value: str | None = None  # значение в ИД
    note: str | None = None  # примечание компьютера
    is_free_search: bool = False  # находка вне матрицы


@dataclass
class ProtocolHeader:
    object_name: str
    address: str
    scenario: str  # e.g. "FULL", "PD_RD_ONLY"
    analysis_date: datetime.date = field(default_factory=datetime.date.today)
    package_id: str | None = None


@dataclass
class ProtocolDocument:
    header: ProtocolHeader
    findings: list[ProtocolFinding] = field(default_factory=list)

    def section_1_deviations(self) -> list[ProtocolFinding]:
        """Section 1: detected violations (CANDIDATE + MISSING_EVIDENCE)."""
        return [f for f in self.findings if f.status in _SECTION_DEVIATIONS]

    def section_2_auto(self) -> list[ProtocolFinding]:
        """Section 2: automatic coincidences."""
        return [f for f in self.findings if f.status in _SECTION_AUTO]

    def section_3_manual(self) -> list[ProtocolFinding]:
        """Section 3: require manual verification."""
        return [f for f in self.findings if f.status in _SECTION_MANUAL]

    def section_4_na(self) -> list[ProtocolFinding]:
        """Section 4: not applicable."""
        return [f for f in self.findings if f.status in _SECTION_NA]

    def section_5_free_search(self) -> list[ProtocolFinding]:
        """Section 5: free-search findings outside the 132-rule matrix."""
        return [f for f in self.findings if f.is_free_search]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to Appendix-2-compatible dict for JSON / DOCX rendering."""
        return {
            "header": {
                "object_name": self.header.object_name,
                "address": self.header.address,
                "scenario": self.header.scenario,
                "analysis_date": self.header.analysis_date.isoformat(),
                "package_id": self.header.package_id,
            },
            "section_1_deviations": [
                _finding_to_dict(f) for f in self.section_1_deviations()
            ],
            "section_2_auto": [
                _finding_to_dict(f) for f in self.section_2_auto()
            ],
            "section_3_manual": [
                _finding_to_dict(f) for f in self.section_3_manual()
            ],
            "section_4_na": [
                _finding_to_dict(f) for f in self.section_4_na()
            ],
            "section_5_free_search": [
                _finding_to_dict(f) for f in self.section_5_free_search()
            ],
            "totals": {
                "deviations": len(self.section_1_deviations()),
                "auto": len(self.section_2_auto()),
                "manual": len(self.section_3_manual()),
                "na": len(self.section_4_na()),
                "free_search": len(self.section_5_free_search()),
            },
        }


def _finding_to_dict(f: ProtocolFinding) -> dict[str, Any]:
    return {
        "parameter_code": f.parameter_code,
        "parameter_name": f.parameter_name,
        "status": f.status.value,
        "section_ref": f.section_ref,
        "pd_value": f.pd_value,
        "rd_value": f.rd_value,
        "id_value": f.id_value,
        "note": f.note,
    }


def build_protocol(
    header: ProtocolHeader,
    findings: Sequence[ProtocolFinding],
) -> ProtocolDocument:
    """Assemble a ProtocolDocument from header + findings."""
    doc = ProtocolDocument(header=header)
    doc.findings.extend(findings)
    return doc
