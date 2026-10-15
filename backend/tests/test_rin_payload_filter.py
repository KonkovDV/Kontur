"""TOP20 #13 P0: в тело outbox/РиН не попадают CANDIDATE/SUSPICION."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from kontur.application.protocol import protocol_for_rin
from kontur.domain.statuses import ProcessState, Scenario
from kontur.infrastructure.db.process_store import (
    MemoryProcessStore,
    ProcessSnapshot,
    protocol_payload_sha256,
)
from kontur.infrastructure.outbox import RecordingPublisher, relay_once_memory


def _snap() -> ProcessSnapshot:
    return ProcessSnapshot(
        process_id="p-rin",
        object_id="obj-rin",
        process_state=ProcessState.FINALIZED,
        scenario=Scenario.SINGLE_ONLY,
        matrix_version="draft-0",
        model_version="none",
        finalized_by="insp-7",
        protocol_id="protocol-p-rin",
    )


def _full_payload() -> dict[str, object]:
    return {
        "protocol_id": "protocol-p-rin",
        "object_id": "obj-rin",
        "version": 1,
        "status": "PROTOCOL_FINALIZED",
        "scenario": "SINGLE_ONLY",
        "upload_status": {"pd": "PD_UPLOADED", "rd": "RD_MISSING", "id": "ID_MISSING"},
        "sections": {
            "completeness": [{"finding_id": "c1", "rule_code": "X", "finding_status": "PRESENT"}],
            "candidates": [
                {
                    "finding_id": "cand-1",
                    "rule_code": "PZ-001",
                    "finding_status": "CANDIDATE",
                    "rationale": "черновик",
                }
            ],
            "confirmed": [
                {
                    "finding_id": "conf-1",
                    "rule_code": "PZ-002",
                    "finding_status": "CONFIRMED_VIOLATION",
                    "rationale": "подтверждено",
                    "versions": {
                        "matrix_version": "draft-0",
                        "rule_version": "1",
                        "model_version": "none",
                    },
                }
            ],
            "negative_verified": [
                {
                    "finding_id": "neg-1",
                    "rule_code": "PZ-003",
                    "finding_status": "NEGATIVE_VERIFIED",
                    "rationale": "отклонено",
                }
            ],
            "suspicions": [
                {
                    "finding_id": "sus-1",
                    "rule_code": "FREE-1",
                    "finding_status": "SUSPICION",
                    "rationale": "гипотеза",
                }
            ],
            "needs_attention": [
                {
                    "finding_id": "att-1",
                    "rule_code": "PZ-004",
                    "finding_status": "ABSTAIN",
                }
            ],
            "missing_evidence": [],
            "preliminary_no_difference": [
                {
                    "finding_id": "auto-1",
                    "rule_code": "PZ-005",
                    "finding_status": "AUTO_NO_DIFFERENCE",
                }
            ],
        },
        "violation_count": 99,
        "versions": {"matrix_version": "draft-0", "model_version": "none"},
        "input_manifest": {"manifest_hash": "a" * 64, "files": [{"file_id": "f1"}]},
    }


def test_protocol_for_rin_drops_candidate_suspicion_and_keeps_versions() -> None:
    rin = protocol_for_rin(_full_payload())
    sections = rin["sections"]
    assert set(sections) == {"confirmed", "negative_verified"}
    assert len(sections["confirmed"]) == 1
    assert sections["confirmed"][0]["finding_status"] == "CONFIRMED_VIOLATION"
    assert len(sections["negative_verified"]) == 1
    assert rin["violation_count"] == 1
    assert rin["versions"]["matrix_version"] == "draft-0"
    assert rin["input_manifest"]["manifest_hash"] == "a" * 64
    blob = json.dumps(rin, ensure_ascii=False)
    assert "CANDIDATE" not in blob
    assert "SUSPICION" not in blob
    assert "AUTO_NO_DIFFERENCE" not in blob
    assert "needs_attention" not in blob
    assert "completeness" not in sections


def test_published_outbox_body_has_no_candidate() -> None:
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    store = MemoryProcessStore()
    store.materialize_finalized(_snap(), _full_payload())
    store._outbox["protocol-p-rin"]["available_at"] = now
    publisher = RecordingPublisher()
    assert relay_once_memory(store, publisher, now) == "DELIVERED"
    assert len(publisher.events) == 1
    _event_id, body = publisher.events[0]
    text = body.decode("utf-8")
    assert "CANDIDATE" not in text
    assert "SUSPICION" not in text
    assert "AUTO_NO_DIFFERENCE" not in text
    parsed = json.loads(text)
    assert "candidates" not in parsed.get("sections", {})
    assert "suspicions" not in parsed.get("sections", {})
    assert parsed["sections"]["confirmed"]
    assert parsed["versions"]
    assert parsed["input_manifest"]
    stored = store.load_protocol("protocol-p-rin")
    assert stored is not None
    assert protocol_payload_sha256(stored) == store._outbox["protocol-p-rin"]["payload_sha256"]


def test_protocol_for_rin_allowlist_drops_empty_and_wrong_status() -> None:
    payload = _full_payload()
    payload["sections"]["confirmed"] = [
        {"finding_id": "ok", "rule_code": "PZ-002", "finding_status": "CONFIRMED_VIOLATION"},
        {"finding_id": "no-status", "rule_code": "PZ-009"},  # нет finding_status
        {"finding_id": "empty", "rule_code": "PZ-010", "finding_status": ""},
        {"finding_id": "wrong-bucket", "rule_code": "PZ-011",
         "finding_status": "NEGATIVE_VERIFIED"},
        {"finding_id": "candidate-in-confirmed", "rule_code": "PZ-012",
         "finding_status": "CANDIDATE"},
    ]
    payload["sections"]["negative_verified"] = [
        {"finding_id": "neg-ok", "rule_code": "PZ-003", "finding_status": "NEGATIVE_VERIFIED"},
        {"finding_id": "confirmed-in-neg", "rule_code": "PZ-013",
         "finding_status": "CONFIRMED_VIOLATION"},
        {"finding_id": "blank", "rule_code": "PZ-014", "finding_status": "   "},
    ]
    rin = protocol_for_rin(payload)
    assert [r["finding_id"] for r in rin["sections"]["confirmed"]] == ["ok"]
    assert [r["finding_id"] for r in rin["sections"]["negative_verified"]] == ["neg-ok"]
    assert rin["violation_count"] == 1
