from fastapi.testclient import TestClient

from app.longitudinal import progression
from app.main import app
from app.repo import MemoryRepo
from app.schemas import CaseInput, VisitIn

client = TestClient(app)


def _mk(patient="p1"):
    r = client.post("/api/cases", json={"patient_ref": patient, "modalities": ["ct"]})
    return r.json()["data"]["id"]


def test_memory_repo_add_and_list_visits():
    import asyncio

    async def run():
        repo = MemoryRepo()
        case = await repo.create_case(CaseInput(patient_ref="p1", modalities=["ct"]))
        v = await repo.add_visit(
            case.id, VisitIn(visit_date="2026-01-01", size_mm=12.0)
        )
        assert v is not None and v.case_id == case.id
        visits = await repo.list_visits(case.id)
        assert len(visits) == 1
        assert visits[0].size_mm == 12.0

    asyncio.run(run())


def test_memory_repo_unknown_case_returns_none():
    import asyncio

    async def run():
        repo = MemoryRepo()
        v = await repo.add_visit("nope", VisitIn(visit_date="2026-01-01"))
        assert v is None
        assert await repo.list_visits("nope") == []

    asyncio.run(run())


def test_progression_growing():
    visits = [
        {"visit_date": "2026-01-01", "size_mm": 10.0},
        {"visit_date": "2026-04-01", "size_mm": 20.0},
    ]
    p = progression(visits)
    assert p["trend"] == "growing"
    assert p["delta_mm"] == 10.0
    assert p["doubling_time_days"] is not None and p["doubling_time_days"] > 0
    assert len(p["series"]) == 2


def test_progression_stable_and_shrinking():
    stable = progression(
        [
            {"visit_date": "2026-01-01", "size_mm": 10.0},
            {"visit_date": "2026-02-01", "size_mm": 10.4},
        ]
    )
    assert stable["trend"] == "stable"
    shrinking = progression(
        [
            {"visit_date": "2026-01-01", "size_mm": 20.0},
            {"visit_date": "2026-02-01", "size_mm": 15.0},
        ]
    )
    assert shrinking["trend"] == "shrinking"


def test_progression_unknown_single_visit():
    p = progression([{"visit_date": "2026-01-01", "size_mm": 8.0}])
    assert p["trend"] == "unknown"
    assert p["delta_mm"] is None


def test_add_visit_api_201_with_location():
    case_id = _mk()
    r = client.post(
        f"/api/cases/{case_id}/visits",
        json={"visit_date": "2026-03-01", "size_mm": 14.5, "notes": "follow-up"},
    )
    assert r.status_code == 201
    assert f"/api/cases/{case_id}/visits" in r.headers["location"]
    body = r.json()["data"]
    assert body["size_mm"] == 14.5
    assert body["case_id"] == case_id


def test_add_visit_404_unknown_case():
    r = client.post(
        "/api/cases/nope/visits", json={"visit_date": "2026-03-01"}
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_list_visits_envelope_with_progression():
    case_id = _mk()
    for d, s in [("2026-01-01", 10), ("2026-05-01", 18)]:
        client.post(
            f"/api/cases/{case_id}/visits", json={"visit_date": d, "size_mm": s}
        )
    r = client.get(f"/api/cases/{case_id}/visits")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["visits"]) == 3, "auto visit 1 + two sized follow-ups"
    assert data["progression"]["trend"] == "growing"
    assert data["progression"]["delta_mm"] == 8.0


def test_list_visits_404_unknown_case():
    r = client.get("/api/cases/nope/visits")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
