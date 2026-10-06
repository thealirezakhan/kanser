import asyncio

from fastapi.testclient import TestClient
from test_swarm import FakeLLM, _case

from app.main import app
from app.pii import get_pii_guard
from app.swarm import run_case

client = TestClient(app)

LABS_CSV = b"name,value,unit\nhemoglobin,11.2,g/dL\ncreatinine,0.9,mg/dL\n"
VCF_TEXT = b"""##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO
12\t25245350\tTP53\tC\tT\t.\t.\tGENE=TP53
"""


def _mk_case(patient="ing1"):
    r = client.post("/api/cases", json={"patient_ref": patient, "modalities": ["ct"]})
    return r.json()["data"]["id"]


def test_ingest_classifies_and_standardizes_labs_csv():
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("panel.csv", LABS_CSV, "text/csv")},
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["kind"] == "labs"
    assert data["standardized"]["labs"]["values"]["hemoglobin"] == "11.2 g/dL"
    assert "sha256" in data


def test_ingest_with_case_id_merges_labs_into_case():
    case_id = _mk_case()
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("panel.csv", LABS_CSV, "text/csv")},
        data={"case_id": case_id},
    )
    assert r.status_code == 201
    assert r.json()["data"]["case_id"] == case_id
    got = client.get(f"/api/cases/{case_id}").json()["data"]
    assert "labs" in got["modalities"]
    assert "hemoglobin" in got["metadata"]["labs_raw"]


def test_ingest_with_case_id_merges_vcf():
    case_id = _mk_case("ing2")
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("tumor.vcf", VCF_TEXT, "text/plain")},
        data={"case_id": case_id},
    )
    assert r.status_code == 201
    got = client.get(f"/api/cases/{case_id}").json()["data"]
    assert "genomics" in got["modalities"]
    assert "TP53" in got["metadata"]["vcf"]


def test_ingest_unknown_case_404():
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("panel.csv", LABS_CSV, "text/csv")},
        data={"case_id": "does-not-exist"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_ingest_without_case_id_still_works():
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("scan.png", b"\x89PNG_fake", "image/png")},
    )
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["kind"] == "ct"
    assert data["case_id"] is None


def test_run_case_emits_standardize_event_first():
    case = _case()
    guard = get_pii_guard()
    final = asyncio.run(
        run_case(case, llm=FakeLLM(), guard=guard, router=None, rag=None)
    )
    assert final["events"][0]["type"] == "standardize"
    assert final["events"][0]["node"] == "standardization"
    assert final["standardized"]["schema_version"] == "1.0"
    assert final["events"][0]["schema_version"] == "1.0"


def test_run_case_seeds_warnings_from_quality_flags():
    case = _case(notes="", modalities=["ct", "notes"])
    guard = get_pii_guard()
    final = asyncio.run(
        run_case(case, llm=FakeLLM(), guard=guard, router=None, rag=None)
    )
    # notes modality declared but empty -> quality warning surfaced
    assert any("notes_empty" in w for w in final["warnings"])
