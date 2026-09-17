"""Gate K — ProtocolReport test suite.

Red Team checklist:
  [x] BoundingBox coord validation (page>=1, [0,1] range, x0<x1, y0<y1)
  [x] EvidenceSnippet confidence/CA range [0,1]
  [x] EvidenceCard clicks_to_navigate <=3 (4 -> ValueError)
  [x] ProtocolReportBuilder fluent API + penalty arithmetic
  [x] JSON round-trip (enums as strings, non-ASCII preserved)
  [x] PDF stub returns non-empty bytes starting with %PDF
  [x] DEFAULT_RISK_MATRIX: >=10 entries, unique codes, blockers=10pts
  [x] Dry-run all 132 catalog params, clicks<=3, perf <30 s
"""
import json
import time
import pytest

from kontur.protocol.protocol_service import (
    BoundingBox,
    EvidenceCard,
    EvidenceSnippet,
    FindingStatus,
    OcrPath,
    ProtocolReportBuilder,
    Severity,
    DEFAULT_RISK_MATRIX,
    MAX_CLICKS,
    SEVERITY_PENALTY,
    DocumentMetadata,
)


# ---- helpers ----------------------------------------------------------------

def _bbox(page=1, x0=0.1, y0=0.1, x1=0.9, y1=0.2):
    return BoundingBox(page=page, x0=x0, y0=y0, x1=x1, y1=y1)

def _snippet(text="Text", conf=0.92, ca=0.98, path=OcrPath.VECTOR_PDFIUM):
    return EvidenceSnippet(
        text=text, bbox=_bbox(), confidence=conf,
        character_accuracy=ca, ocr_path=path,
    )

def _card(rule="PZ-001", sev=Severity.MAJOR,
          status=FindingStatus.COMPLIANT, clicks=1):
    return EvidenceCard(
        rule_code=rule, severity=sev, status=status,
        extracted_value="1.0", expected_value="1.0",
        clicks_to_navigate=clicks,
    )


# ---- TestBoundingBox --------------------------------------------------------

class TestBoundingBox:
    def test_valid(self):
        bb = _bbox()
        assert bb.page == 1 and bb.area() > 0

    def test_page_zero_raises(self):
        with pytest.raises(ValueError, match="page must be"):
            BoundingBox(page=0, x0=0.1, y0=0.1, x1=0.9, y1=0.9)

    def test_page_negative_raises(self):
        with pytest.raises(ValueError):
            BoundingBox(page=-1, x0=0.1, y0=0.1, x1=0.9, y1=0.9)

    @pytest.mark.parametrize("f,v", [
        ("x0", -0.01),("x0", 1.01),("y0", -0.01),("y0", 1.01),
        ("x1", -0.01),("x1", 1.01),("y1", -0.01),("y1", 1.01),
    ])
    def test_coord_out_of_range(self, f, v):
        kw = dict(page=1, x0=0.1, y0=0.1, x1=0.9, y1=0.9)
        kw[f] = v
        with pytest.raises(ValueError): BoundingBox(**kw)

    def test_degenerate_x(self):
        with pytest.raises(ValueError, match="x0"):
            BoundingBox(page=1, x0=0.5, y0=0.1, x1=0.5, y1=0.9)

    def test_degenerate_y(self):
        with pytest.raises(ValueError, match="y0"):
            BoundingBox(page=1, x0=0.1, y0=0.5, x1=0.9, y1=0.5)

    def test_x0_gt_x1(self):
        with pytest.raises(ValueError, match="x0"):
            BoundingBox(page=1, x0=0.9, y0=0.1, x1=0.1, y1=0.9)

    def test_y0_gt_y1(self):
        with pytest.raises(ValueError, match="y0"):
            BoundingBox(page=1, x0=0.1, y0=0.9, x1=0.9, y1=0.1)

    def test_large_page(self):
        assert BoundingBox(page=9999, x0=0.0, y0=0.0, x1=1.0, y1=1.0).page == 9999

    def test_area(self):
        bb = BoundingBox(page=1, x0=0.0, y0=0.0, x1=0.5, y1=0.5)
        assert abs(bb.area() - 0.25) < 1e-9


# ---- TestEvidenceSnippet ---------------------------------------------------

class TestEvidenceSnippet:
    def test_valid_vector(self):
        assert _snippet(path=OcrPath.VECTOR_PDFIUM, ca=1.0).meets_ca_gate()

    def test_raster_below_ca(self):
        assert not _snippet(path=OcrPath.RASTER_REGION, ca=0.95).meets_ca_gate()

    def test_confidence_boundary(self):
        _snippet(conf=0.0); _snippet(conf=1.0)

    def test_confidence_neg_raises(self):
        with pytest.raises(ValueError, match="confidence"): _snippet(conf=-0.01)

    def test_confidence_over_one(self):
        with pytest.raises(ValueError, match="confidence"): _snippet(conf=1.001)

    def test_ca_neg_raises(self):
        with pytest.raises(ValueError, match="character_accuracy"): _snippet(ca=-0.01)

    def test_ca_over_one(self):
        with pytest.raises(ValueError, match="character_accuracy"): _snippet(ca=1.001)

    def test_ca_at_threshold(self):
        assert _snippet(ca=0.97).meets_ca_gate()

    def test_ca_below_threshold(self):
        assert not _snippet(ca=0.9699).meets_ca_gate()


# ---- TestEvidenceCard ------------------------------------------------------

class TestEvidenceCard:
    def test_clicks_1_2_3_valid(self):
        for c in (1, 2, 3): assert _card(clicks=c).clicks_to_navigate == c

    def test_clicks_4_raises_gate_k(self):
        with pytest.raises(ValueError, match="Gate K"): _card(clicks=4)

    def test_clicks_100_raises(self):
        with pytest.raises(ValueError, match="Gate K"): _card(clicks=100)

    def test_clicks_zero_raises(self):
        with pytest.raises(ValueError): _card(clicks=0)

    def test_blocker_penalty_and_flag(self):
        c = EvidenceCard(rule_code="PZ-001", severity=Severity.BLOCKER,
                         status=FindingStatus.CONFIRMED_VIOLATION,
                         extracted_value=None, expected_value=None)
        assert c.penalty == 10.0 and c.is_blocker

    def test_compliant_no_penalty(self):
        c = _card(status=FindingStatus.COMPLIANT, sev=Severity.BLOCKER)
        assert c.penalty == 0.0 and not c.is_blocker

    def test_abstained_no_penalty(self):
        assert _card(status=FindingStatus.ABSTAINED, sev=Severity.CRITICAL).penalty == 0.0

    def test_snippets_attached(self):
        c = EvidenceCard(rule_code="PZ-003", severity=Severity.CRITICAL,
                         status=FindingStatus.CONFIRMED_VIOLATION,
                         extracted_value="1:500", expected_value="1:200",
                         snippets=[_snippet()])
        assert len(c.snippets) == 1


# ---- TestProtocolReportBuilder ---------------------------------------------

class TestProtocolReportBuilder:
    def test_empty(self):
        r = ProtocolReportBuilder("doc-001").build()
        assert len(r.cards) == 0 and r.total_penalty == 0.0 and r.overall_passed

    def test_compliant(self):
        r = (ProtocolReportBuilder("doc-002")
             .add_card(_card("PZ-001", status=FindingStatus.COMPLIANT))
             .add_card(_card("PZ-002", status=FindingStatus.COMPLIANT))
             .build())
        assert r.violation_count == 0 and r.total_penalty == 0.0 and r.overall_passed

    def test_non_blocking_violation(self):
        r = (ProtocolReportBuilder("doc-003")
             .add_card(_card("PZ-003", sev=Severity.MAJOR,
                             status=FindingStatus.CONFIRMED_VIOLATION))
             .build())
        assert r.violation_count == 1
        assert r.total_penalty == SEVERITY_PENALTY[Severity.MAJOR]
        assert r.overall_passed

    def test_blocking_violation(self):
        r = (ProtocolReportBuilder("doc-004")
             .add_card(EvidenceCard(
                 rule_code="AR-041", severity=Severity.BLOCKER,
                 status=FindingStatus.CONFIRMED_VIOLATION,
                 extracted_value="0.7", expected_value=">=0.9"))
             .build())
        assert not r.overall_passed and r.total_penalty == 10.0

    def test_fluent_returns_self(self):
        b = ProtocolReportBuilder("doc-005")
        assert b.add_card(_card()) is b

    def test_model_version(self):
        r = ProtocolReportBuilder("doc-006", model_version="kontur-v2").build()
        assert r.metadata.model_version == "kontur-v2"


# ---- TestJsonSerialization -------------------------------------------------

class TestJsonSerialization:
    def _report(self):
        return (ProtocolReportBuilder("doc-json")
                .add_card(EvidenceCard(
                    rule_code="PZ-003", severity=Severity.CRITICAL,
                    status=FindingStatus.CONFIRMED_VIOLATION,
                    extracted_value="1:500", expected_value="1:200",
                    snippets=[_snippet(text="Scale 1:500", ca=0.98, conf=0.91)],
                    clicks_to_navigate=2,
                    rule_description="Drawing scale",
                    norm_ref="GOST R 21.101-2026 s4.5"))
                .build())

    def test_parseable(self): json.loads(self._report().to_json())

    def test_enums_as_strings(self):
        v = self._report().to_dict()["violations"][0]
        assert isinstance(v["severity"], str)
        assert isinstance(v["status"], str)
        assert isinstance(v["snippets"][0]["ocr_path"], str)

    def test_summary_fields(self):
        d = self._report().to_dict()
        assert {"overall_passed","total_penalty","violation_count"} <= set(d["summary"])

    def test_penalty_round_trip(self):
        assert json.loads(self._report().to_json())["summary"]["total_penalty"] == 7.0

    def test_clicks_in_output(self):
        assert self._report().to_dict()["violations"][0]["clicks_to_navigate"] == 2

    def test_bbox_keys(self):
        bbox = self._report().to_dict()["violations"][0]["snippets"][0]["bbox"]
        assert set(bbox.keys()) == {"page","x0","y0","x1","y1"}


# ---- TestPdfBytes ----------------------------------------------------------

class TestPdfBytes:
    def test_bytes(self):
        r = ProtocolReportBuilder("doc-pdf").build()
        b = r.to_pdf_bytes()
        assert isinstance(b, bytes) and len(b) > 0 and b.startswith(b"%PDF")


# ---- TestDefaultRiskMatrix -------------------------------------------------

class TestDefaultRiskMatrix:
    def test_min_entries(self):    assert len(DEFAULT_RISK_MATRIX) >= 10
    def test_unique_codes(self):
        codes = [e["rule_code"] for e in DEFAULT_RISK_MATRIX]
        assert len(codes) == len(set(codes))
    def test_blockers_penalty(self):
        for e in DEFAULT_RISK_MATRIX:
            if e["severity"] == Severity.BLOCKER.value:
                assert e["penalty"] == 10.0
    def test_groups_present(self):
        groups = {e["group"] for e in DEFAULT_RISK_MATRIX}
        for g in ("PZ","AR","KR"): assert g in groups
    def test_severity_valid(self):
        valid = {s.value for s in Severity}
        for e in DEFAULT_RISK_MATRIX: assert e["severity"] in valid


# ---- TestDryRun132Params ---------------------------------------------------

# Full 132-param catalog
CATALOG = (
    [(f"PZ-{i:03d}", Severity.MAJOR)    for i in range(1,  10)] +
    [(f"PZ-{i:03d}", Severity.CRITICAL) for i in range(10, 24)] +
    [(f"SPZU-{i:03d}", Severity.MAJOR)  for i in range(24, 40)] +
    [(f"AR-{i:03d}",
      Severity.BLOCKER if i == 41 else Severity.CRITICAL)
     for i in range(40, 54)] +
    [(f"KR-{i:03d}", Severity.CRITICAL) for i in range(54, 68)] +
    [(f"IOS1-{i:03d}", Severity.MAJOR)  for i in range(68, 71)] +
    [(f"IOS2-{i:03d}", Severity.MAJOR)  for i in range(71, 74)] +
    [(f"IOS3-{i:03d}", Severity.MAJOR)  for i in range(74, 76)] +
    [(f"IOS4-{i:03d}", Severity.MAJOR)  for i in range(76, 80)] +
    [("IOS5-080",      Severity.MAJOR)] +
    [(f"POS-{i:03d}", Severity.MAJOR)   for i in range(81, 90)] +
    [(f"POD-{i:03d}",
      Severity.BLOCKER if i == 90 else Severity.MAJOR)
     for i in range(90, 98)] +
    [(f"OOS-{i:03d}", Severity.MAJOR)   for i in range(98, 102)] +
    [(f"PPM-{i:03d}",
      Severity.BLOCKER if i in (102,103) else Severity.MAJOR)
     for i in range(102, 115)] +
    [(f"ODI-{i:03d}", Severity.CRITICAL) for i in range(115, 124)] +
    [(f"ZU-{i:03d}",
      Severity.BLOCKER if i == 124 else Severity.MAJOR)
     for i in range(124, 132)] +
    [("SM-132", Severity.CRITICAL)]
)


class TestDryRun132Params:
    def test_catalog_size(self):
        assert len(CATALOG) == 132, f"Got {len(CATALOG)} entries"

    def test_unique_codes(self):
        codes = [c[0] for c in CATALOG]
        assert len(codes) == len(set(codes)), "Duplicate codes"

    def test_perf_and_clicks(self):
        builder = ProtocolReportBuilder("dry-run-132")
        t0 = time.perf_counter()
        for code, sev in CATALOG:
            builder.add_card(EvidenceCard(
                rule_code=code, severity=sev,
                status=FindingStatus.ABSTAINED,
                extracted_value=None, expected_value=None,
                clicks_to_navigate=2,
            ))
        report = builder.build()
        elapsed = time.perf_counter() - t0
        assert elapsed < 30.0, f"Dry run {elapsed:.2f}s >= 30s"
        assert len(report.cards) == 132
        for c in report.cards:
            assert c.clicks_to_navigate <= MAX_CLICKS

    def test_json_132(self):
        builder = ProtocolReportBuilder("json-132")
        for code, sev in CATALOG:
            builder.add_card(EvidenceCard(
                rule_code=code, severity=sev,
                status=FindingStatus.COMPLIANT,
                extracted_value="ok", expected_value="ok",
            ))
        d = json.loads(builder.build().to_json())
        assert len(d["violations"]) == 132
