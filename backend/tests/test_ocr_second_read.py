"""Region-crop dual-read: disagreement → ABSTAIN, без pdf_bytes путь не меняется."""

from __future__ import annotations

from pathlib import Path

import pytest

from kontur.application.evaluate import StagePage, evaluate_rule
from kontur.application.extractors.number import PageToken
from kontur.domain.coordinates import PageFrame
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef, ExtractionEngine
from kontur.domain.statuses import Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import FileRuleRegistry

REPO = Path(__file__).resolve().parents[2]
HASH = "b" * 64
_REGISTRY = FileRuleRegistry(REPO / "data" / "matrix")


def _tok(text: str, x: float, y: float = 0.40) -> PageToken:
    polygon = ((x, y), (x + 0.10, y), (x + 0.10, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)


def _line(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(word, 0.08 + index * 0.14) for index, word in enumerate(words))


def _doc(stage: DocStage) -> DocumentRef:
    return DocumentRef(
        file_id=f"ocr-{stage.value.lower()}",
        file_hash=HASH,
        doc_stage=stage,
        document_code="12345-PZ",
        revision="1",
        approval_status=ApprovalStatus.APPROVED,
        sheet="ОД",
    )


def _completeness() -> dict[DocStage, Completeness]:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.UPLOADED,
        DocStage.ID: Completeness.MISSING,
    }


def _page(stage: DocStage, *words: str) -> StagePage:
    frame = PageFrame(media=(0.0, 0.0, 1.0, 1.0), crop=(0.0, 0.0, 1.0, 1.0), rotate=0)
    return StagePage(
        document=_doc(stage),
        tokens=_line(*words),
        pdf_bytes=b"%PDF-mock",
        frames=(frame,),
    )


def test_ocr_region_disagreement_is_abstain(monkeypatch: pytest.MonkeyPatch) -> None:
    poly = ((0.36, 0.40), (0.46, 0.40), (0.46, 0.44), (0.36, 0.44))
    other = PageToken("1100", 1, poly, poly, engine=ExtractionEngine.OCR)
    monkeypatch.setattr("kontur.application.evaluate.tesseract_available", lambda: True)
    monkeypatch.setattr(
        "kontur.application.evaluate.ocr_region_crop",
        lambda *_args, **_kwargs: (other,),
    )
    rule = _REGISTRY.get("PZ-001")
    cells = ("Площадь", "застройки", "1250,5")
    pages = {
        DocStage.PD: _page(DocStage.PD, *cells),
        DocStage.RD: _page(DocStage.RD, *cells),
    }
    result = evaluate_rule(
        rule, object_id="obj-ocr-dr", pages=pages, completeness=_completeness()
    )
    assert result.finding.finding_status is FindingStatus.ABSTAIN


def test_ocr_region_agreement_keeps_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    poly = ((0.36, 0.40), (0.46, 0.40), (0.46, 0.44), (0.36, 0.44))
    same = PageToken("1250,5", 1, poly, poly, engine=ExtractionEngine.OCR)
    monkeypatch.setattr("kontur.application.evaluate.tesseract_available", lambda: True)
    monkeypatch.setattr(
        "kontur.application.evaluate.ocr_region_crop",
        lambda *_args, **_kwargs: (same,),
    )
    rule = _REGISTRY.get("PZ-001")
    cells = ("Площадь", "застройки", "1250,5")
    pages = {
        DocStage.PD: _page(DocStage.PD, *cells),
        DocStage.RD: _page(DocStage.RD, *cells),
    }
    result = evaluate_rule(
        rule, object_id="obj-ocr-ok", pages=pages, completeness=_completeness()
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE


def test_empty_ocr_crop_does_not_force_abstain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("kontur.application.evaluate.tesseract_available", lambda: True)
    monkeypatch.setattr(
        "kontur.application.evaluate.ocr_region_crop",
        lambda *_args, **_kwargs: (),
    )
    rule = _REGISTRY.get("PZ-001")
    cells = ("Площадь", "застройки", "1250,5")
    pages = {
        DocStage.PD: _page(DocStage.PD, *cells),
        DocStage.RD: _page(DocStage.RD, *cells),
    }
    result = evaluate_rule(
        rule, object_id="obj-ocr-empty", pages=pages, completeness=_completeness()
    )
    assert result.finding.finding_status is FindingStatus.AUTO_NO_DIFFERENCE
