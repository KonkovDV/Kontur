"""Signed-JWT regression at the HTTP object-scope boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from kontur.application.runtime import ProcessWorkspace
from kontur.presentation.api import app

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
ISSUER = "https://issuer.test/"
AUDIENCE = "kontur-api"


def _bearer(private: object, object_id: str) -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "insp-7",
            "roles": ["INSPECTOR"],
            "object_id": object_id,
            "nbf": now - timedelta(seconds=1),
            "exp": now + timedelta(minutes=5),
        },
        private,
        algorithm="RS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_valid_wrong_object_is_403_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    monkeypatch.setenv("KONTUR_ALLOW_INSECURE_DEV_AUTH", "false")
    monkeypatch.setenv("KONTUR_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("KONTUR_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("KONTUR_JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("KONTUR_JWT_PUBLIC_KEY", public)
    app.state.workspace = ProcessWorkspace()
    client = TestClient(app)

    created = client.post(
        "/api/v1/documents/upload",
        headers=_bearer(private, "OBJ-001"),
        data={"object_id": "OBJ-001", "doc_stage": "PD"},
        files=[("files", ("pz.pdf", PDF, "application/pdf"))],
    )
    assert created.status_code == 202
    process_id = created.json()["process_id"]
    record = app.state.workspace.get(process_id)
    assert record is not None
    snapshot = record.to_status()
    files_before = tuple(record.files)
    audit_before = tuple(record.audit.records)

    denied = client.get(
        f"/api/v1/processes/{process_id}/status",
        headers=_bearer(private, "OBJ-OTHER"),
    )
    assert denied.status_code == 403
    assert denied.json() == {"detail": "access denied"}
    assert "OBJ-001" not in denied.text
    assert "OBJ-OTHER" not in denied.text
    assert record.to_status() == snapshot
    assert tuple(record.files) == files_before
    assert tuple(record.audit.records) == audit_before
