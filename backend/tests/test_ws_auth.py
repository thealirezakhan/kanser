import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth_enabled(monkeypatch):
    monkeypatch.setenv("DISABLE_AUTH", "0")


def _login() -> str:
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    return r.json()["data"]["token"]


def test_login_returns_jwt():
    token = _login()
    assert jwt.decode(token, options={"verify_signature": False})["sub"] == "admin"


def test_bad_password_401_envelope():
    r = client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_protected_route_requires_token():
    r = client.get("/api/cases")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_protected_route_with_token():
    token = _login()
    r = client.get("/api/cases", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_health_stays_public():
    assert client.get("/api/health").status_code == 200


def test_ws_streams_agent_events_until_complete():
    # single portal: diagnose's background task must outlive the POST
    with client:
        token = _login()
        headers = {"Authorization": f"Bearer {token}"}
        cid = client.post(
            "/api/cases",
            json={"patient_ref": "w", "modalities": ["ct", "notes"], "clinical_notes": "nodule"},
            headers=headers,
        ).json()["data"]["id"]
        run_id = client.post(
            f"/api/cases/{cid}/diagnose", headers=headers
        ).json()["data"]["run_id"]

        with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
            ws.send_json({"type": "auth", "token": token})
            seen = []
            deadline = time.time() + 30
            while time.time() < deadline:
                ev = ws.receive_json()
                seen.append(ev.get("type"))
                if ev.get("type") == "run_completed":
                    break

    assert "agent_step" in seen
    assert "evidence" in seen
    assert seen[-1] == "run_completed"


def test_ws_unknown_run_closed():
    from starlette.websockets import WebSocketDisconnect

    token = _login()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/runs/does-not-exist") as ws:
            ws.send_json({"type": "auth", "token": token})
            ws.receive_json()
