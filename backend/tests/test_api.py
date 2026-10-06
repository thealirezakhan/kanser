from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_create_case_201_with_location():
    r = client.post("/api/cases", json={"patient_ref": "abc", "modalities": ["ct"]})
    assert r.status_code == 201
    assert "location" in r.headers
    body = r.json()["data"]
    assert body["patient_ref"] == "abc"
    assert body["id"]


def test_create_case_validation_envelope():
    r = client.post("/api/cases", json={"modalities": []})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert "message" in err


def test_get_case_404_envelope():
    r = client.get("/api/cases/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_list_cases():
    client.post("/api/cases", json={"patient_ref": "x", "modalities": []})
    r = client.get("/api/cases")
    assert r.status_code == 200
    assert isinstance(r.json()["data"], list)


def test_diagnose_accepted():
    r = client.post("/api/cases", json={"patient_ref": "y", "modalities": ["ct"]})
    cid = r.json()["data"]["id"]
    r = client.post(f"/api/cases/{cid}/diagnose")
    assert r.status_code == 202
    assert r.json()["data"]["run_id"]


def test_run_id_derived_from_patient_and_case():
    r = client.post(
        "/api/cases", json={"patient_ref": "P-1024", "modalities": ["ct"]}
    )
    cid = r.json()["data"]["id"]
    rid = client.post(f"/api/cases/{cid}/diagnose").json()["data"]["run_id"]
    # meaningful: patient slug + case prefix + timestamp, not opaque hex
    assert rid.startswith("p-1024-")
    assert cid[:6] in rid
    assert not all(c in "0123456789abcdef" for c in rid)
