import asyncio
import os
import socket
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runs import run_store

client = TestClient(app)


def _pg_up() -> bool:
    try:
        with socket.create_connection(("localhost", 5432), timeout=1):
            return True
    except OSError:
        return False


def test_list_runs_envelope():
    rid = uuid.uuid4().hex
    run_store.create(rid)
    run_store.update(rid, status="completed", result={"consensus": {"diagnosis": "x"}})
    r = client.get("/api/runs")
    assert r.status_code == 200
    runs = r.json()["data"]["runs"]
    assert any(x["run_id"] == rid for x in runs)
    target = next(x for x in runs if x["run_id"] == rid)
    assert target["status"] == "completed"
    assert "updated_at" in target


def test_run_hydrated_from_db_after_restart():
    # opt-in: hermetic tests run without DATABASE_URL (see conftest)
    if not _pg_up() or os.environ.get("KANSER_TEST_DB") != "1":
        pytest.skip("set KANSER_TEST_DB=1 with postgres up")
    rid = uuid.uuid4().hex
    run_store.create(rid)
    run_store.update(rid, status="completed", result={"consensus": {"diagnosis": "y"}})
    run_store.push_event(rid, {"type": "run_completed"})
    asyncio.run(run_store.persist(rid))
    run_store._runs.pop(rid, None)
    r = client.get(f"/api/runs/{rid}")
    assert r.status_code == 200
    snap = r.json()["data"]
    assert snap["status"] == "completed"
    assert snap["run_id"] == rid


def test_get_run_404_envelope():
    r = client.get("/api/runs/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_evidence_search_envelope():
    r = client.get("/api/evidence/search", params={"q": "stage I adenocarcinoma"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert "verified" in data
    assert isinstance(data["verified"], list)
    assert "dropped" in data


def test_evidence_search_requires_query():
    r = client.get("/api/evidence/search")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_system_status_no_secret_leak():
    r = client.get("/api/system/status")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "ok"
    assert data["llm"] in ("local", "groq")
    assert "api_key" not in r.text.lower()
    assert "kanser:" not in r.text  # no DSN credentials


def test_alerts_envelope():
    rid = uuid.uuid4().hex
    run_store.create(rid)
    run_store.update(rid, status="failed")
    r = client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()["data"]
    assert "failed_runs" in data
    assert "high_risk_cases" in data
    assert any(x["run_id"] == rid for x in data["failed_runs"])
