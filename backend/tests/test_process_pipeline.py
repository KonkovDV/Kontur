"""Пайплайн после загрузки: матрица на векторном PDF, без человеческих вердиктов."""

from __future__ import annotations

from test_pdf_tokens import ascii_pdf, empty_pdf

from kontur.application.process_pipeline import PipelineFile, run_process_pipeline
from kontur.application.scenarios import CompletenessMap
from kontur.domain.models import DocStage
from kontur.domain.statuses import HUMAN_ONLY_STATUSES, Completeness, FindingStatus
from kontur.infrastructure.matrix.registry import EXPECTED_PARAM_COUNT
from kontur.infrastructure.pdfium_tokens import file_sha256


def _completeness_pd() -> CompletenessMap:
    return {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }


def test_pipeline_evaluates_compiled_matrix_without_human_verdicts() -> None:
    data = ascii_pdf("CODE 12345-PZ Rev 2 Sheet 1")
    digest = file_sha256(data)
    item = PipelineFile(
        file_id="f-pd",
        file_hash=digest,
        filename="pz.pdf",
        doc_stage=DocStage.PD,
    )
    report = run_process_pipeline(
        object_id="obj-pipe",
        completeness=_completeness_pd(),
        files=(item,),
        blobs={"f-pd": data},
    )
    assert report.rules_evaluated == EXPECTED_PARAM_COUNT
    assert report.pages_built == 1
    assert len(report.findings) == EXPECTED_PARAM_COUNT
    assert all(item.finding_status not in HUMAN_ONLY_STATUSES for item in report.findings)
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        item.finding_status for item in report.findings
    }
    assert {item.finding_id for item in report.findings} == {
        f"pipe-{finding.rule_code}" for finding in report.findings
    }


def test_pipeline_does_not_treat_raster_page_as_ocr_success() -> None:
    data = empty_pdf()
    digest = file_sha256(data)
    item = PipelineFile(
        file_id="f-empty",
        file_hash=digest,
        filename="scan.pdf",
        doc_stage=DocStage.PD,
    )
    report = run_process_pipeline(
        object_id="obj-raster",
        completeness=_completeness_pd(),
        files=(item,),
        blobs={"f-empty": data},
    )
    assert report.pages_built == 1
    assert report.rules_evaluated == EXPECTED_PARAM_COUNT
    assert FindingStatus.CONFIRMED_VIOLATION not in {
        item.finding_status for item in report.findings
    }


def test_corrupt_pdf_is_parse_error_not_violation() -> None:
    item = PipelineFile(
        file_id="f-bad",
        file_hash="a" * 64,
        filename="bad.pdf",
        doc_stage=DocStage.PD,
    )
    report = run_process_pipeline(
        object_id="obj-bad",
        completeness=_completeness_pd(),
        files=(item,),
        blobs={"f-bad": b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"},
    )
    assert report.parse_errors
    assert report.pages_built == 0
    assert report.rules_evaluated == EXPECTED_PARAM_COUNT
    assert all(item.finding_status not in HUMAN_ONLY_STATUSES for item in report.findings)
