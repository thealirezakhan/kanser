"""GAP-014 remainder: audit entries, per-case authz, WS ticket auth, upload cap."""

import json

import pytest
from fastapi.testclient import TestClient

from app.auth import create_token
from app.main import app


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DISABLE_AUTH", "0")
    monkeypatch.setenv("AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    return TestClient(app), tmp_path / "audit.jsonl"


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_case_access_writes_audit_entries(auth_client):
    client, audit_path = auth_client
    token = create_token("admin")
    cid = (
        client.post(
            "/api/cases",
            json={"patient_ref": "p1", "modalities": ["ct"]},
            headers=_h(token),
        ).json()["data"]["id"]
    )
    client.get(f"/api/cases/{cid}", headers=_h(token))
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    actions = [e["action"] for e in events]
    assert "case.create" in actions
    assert "case.read" in actions
    reader = next(e for e in events if e["action"] == "case.read")
    assert reader["actor"] == "admin"
    assert reader["resource"] == cid
    assert reader["at"]


def test_cross_user_case_read_forbidden(auth_client):
    client, _ = auth_client
    tok_a = create_token("user_a")
    tok_b = create_token("user_b")
    cid = (
        client.post(
            "/api/cases",
            json={"patient_ref": "pa", "modalities": ["ct"]},
            headers=_h(tok_a),
        ).json()["data"]["id"]
    )
    assert client.get(f"/api/cases/{cid}", headers=_h(tok_a)).status_code == 200
    r = client.get(f"/api/cases/{cid}", headers=_h(tok_b))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    # list excludes other users' cases
    listing = client.get("/api/cases", headers=_h(tok_b)).json()["data"]
    assert all(c["id"] != cid for c in listing)


def test_ws_rejects_message_without_auth_first(auth_client):
    from starlette.websockets import WebSocketDisconnect

    client, _ = auth_client
    with client.websocket_connect("/ws/runs/none") as ws:
        ws.send_json({"type": "run_subscribe"})
        with pytest.raises(WebSocketDisconnect):  # close before any data
            ws.receive_json()


def test_ws_accepts_auth_first_message(auth_client):
    from starlette.websockets import WebSocketDisconnect

    client, _ = auth_client
    token = create_token("admin")
    with client.websocket_connect("/ws/runs/none") as ws:
        ws.send_json({"type": "auth", "token": token})
        ws.send_json({"type": "run_subscribe"})
        # auth ok -> unknown run gives 4404, never 4401
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code != 4401


def test_upload_size_cap(auth_client, monkeypatch):
    client, _ = auth_client
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "64")
    token = create_token("admin")
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("big.txt", b"x" * 100, "text/plain")},
        headers=_h(token),
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
