"""TOP20 #10 chunk A/D: completeness из каталога + 5 таблиц / 2 раздела."""

from __future__ import annotations

from kontur.application.completeness_catalog import (
    completeness_rows_from_catalog,
    load_sections_catalog,
)
from kontur.application.protocol import assemble_protocol, protocol_for_http
from kontur.application.protocol_export import TABLES, render_docx, render_pdf, render_xml
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness, ProcessState

HASH = "a" * 64


def _completeness(
    pd: Completeness = Completeness.MISSING,
    rd: Completeness = Completeness.MISSING,
    id: Completeness = Completeness.MISSING,
) -> dict[DocStage, Completeness]:
    return {DocStage.PD: pd, DocStage.RD: rd, DocStage.ID: id}


def test_catalog_loads_tz_sections() -> None:
    catalog = load_sections_catalog()
    codes = {str(item["code"]) for item in catalog}
    assert "КР" in codes and "ПЗ" in codes and "СМ" in codes
    assert len(catalog) >= 10


def test_missing_stage_lists_catalog_as_non_violations() -> None:
    rows = completeness_rows_from_catalog(
        _completeness(pd=Completeness.UPLOADED, rd=Completeness.MISSING)
    )
    assert rows
    assert all(row["counts_as_violation"] is False for row in rows)
    missing = [row for row in rows if row["outcome"] == "MISSING"]
    uploaded = [row for row in rows if row["outcome"] == "STAGE_UPLOADED_NOT_VERIFIED"]
    assert missing and all(row["stage"] in {"RD", "ID"} for row in missing)
    assert uploaded and all(row["stage"] == "PD" for row in uploaded)
    assert all(row["outcome"] != "PRESENT" for row in rows)


def test_assemble_fills_completeness_and_keeps_violation_count() -> None:
    payload = assemble_protocol(
        protocol_id="protocol-p10",
        object_id="obj-1",
        findings=(),
        completeness=_completeness(pd=Completeness.PARTIAL),
        files=[],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        process_state=ProcessState.READY,
        input_manifest_hash=HASH,
    )
    completeness = payload["sections"]["completeness"]
    assert isinstance(completeness, list) and len(completeness) > 0
    assert payload["violation_count"] == 0
    assert all(row["counts_as_violation"] is False for row in completeness)
    wire = protocol_for_http(payload)
    assert "preliminary_no_difference" not in wire["sections"]
    assert "AUTO_NO_DIFFERENCE" not in str(wire)


def test_snapshot_five_tz_tables_and_two_sections() -> None:
    """D: 5 таблиц ТЗ + upload_status + check_type; extras помечены."""

    tz_tables = (
        "completeness",
        "candidates",
        "confirmed",
        "negative_verified",
        "suspicions",
    )
    extras = ("missing_evidence", "needs_attention")
    assert all(name in TABLES for name in tz_tables + extras)

    payload = assemble_protocol(
        protocol_id="protocol-snap",
        object_id="obj-snap",
        findings=(),
        completeness=_completeness(pd=Completeness.UPLOADED, rd=Completeness.UPLOADED),
        files=[{"file_id": "f1", "file_hash": HASH}],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        process_state=ProcessState.COMPLETED,
        input_manifest_hash=HASH,
    )
    wire = protocol_for_http(payload)
    sections = wire["sections"]
    assert set(tz_tables).issubset(sections)
    assert "upload_status" in wire and "scenario" in wire
    assert wire["upload_status"]["pd"]
    # extras may be empty lists but keys present on assemble
    assert "missing_evidence" in sections and "needs_attention" in sections

    xml = render_xml(wire).decode("utf-8")
    assert "<upload_status" in xml and "<check_type>" in xml
    for name in tz_tables:
        assert f'name="{name}"' in xml
    assert "AUTO_NO_DIFFERENCE" not in xml

    docx = render_docx(wire)
    assert b"AUTO_NO_DIFFERENCE" not in docx
    assert render_pdf(wire).startswith(b"%PDF")
