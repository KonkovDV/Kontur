"""Группы доказательств переживают рестарт ядра (то же хранилище, что снимок процесса)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pdf_fixtures import contest_slice_font

from kontur.application.runtime import ProcessWorkspace
from kontur.domain.state_machines import Actor
from kontur.evaluation.demo_kit import DEMO_OBJECT_ID, ETALON_FILE_ID, install_demo_kit
from kontur.infrastructure.db.evidence_codec import decode_group, encode_group
from kontur.infrastructure.db.process_store import MemoryProcessStore
from kontur.infrastructure.object_store import MemoryObjectStore
from kontur.presentation.api import app

assert contest_slice_font() is not None

INSPECTOR = Actor(actor_id="insp", is_human=True)


def _restart(store: MemoryProcessStore, objects: MemoryObjectStore) -> ProcessWorkspace:
    return ProcessWorkspace(store=store, objects=objects)


def _selected(workspace: ProcessWorkspace):  # type: ignore[no-untyped-def]
    record = install_demo_kit(workspace, DEMO_OBJECT_ID)
    return workspace.select_revision(
        record.process_id, ETALON_FILE_ID, actor=INSPECTOR, comment="Утверждённая редакция."
    )


def test_codec_round_trips_every_demo_group() -> None:
    record = _selected(ProcessWorkspace())
    assert record.evidence_groups
    for group in record.evidence_groups.values():
        assert decode_group(json.loads(json.dumps(encode_group(group)))) == group


def test_evidence_groups_survive_restart_after_pipeline_and_selection() -> None:
    store, objects = MemoryProcessStore(), MemoryObjectStore()
    first = ProcessWorkspace(store=store, objects=objects)
    record = install_demo_kit(first, DEMO_OBJECT_ID)
    after_kit = dict(record.evidence_groups)
    assert _restart(store, objects).get(record.process_id).evidence_groups == after_kit  # type: ignore[union-attr]

    selected = first.select_revision(
        record.process_id, ETALON_FILE_ID, actor=INSPECTOR, comment="Утверждённая редакция."
    )
    restored = _restart(store, objects).get(record.process_id)
    assert restored is not None
    assert selected.evidence_groups
    assert restored.evidence_groups == selected.evidence_groups
    assert restored.evidence_groups != after_kit


def test_findings_places_after_restart_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "true")
    store, objects = MemoryProcessStore(), MemoryObjectStore()
    record = _selected(ProcessWorkspace(store=store, objects=objects))
    app.state.workspace = _restart(store, objects)
    headers = {"Authorization": f"Bearer insp@{DEMO_OBJECT_ID}/INSPECTOR"}
    response = TestClient(app).get(
        f"/api/v1/processes/{record.process_id}/findings", headers=headers
    )
    assert response.status_code == 200
    with_group = [row for row in response.json()["findings"] if row["evidence_group_id"]]
    assert with_group
    # places == null значит «группы нет в памяти процесса» — после рестарта так быть не должно.
    assert all(row["places"] is not None for row in with_group)
