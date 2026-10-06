"""Evidence findings: extraction with provenance, verification, contradictions."""

from fastapi.testclient import TestClient

from app.conflicts import detect_conflicts
from app.findings import extract_findings
from app.main import app

client = TestClient(app)


# --- extraction (deterministic, no LLM) -------------------------------------


def test_extract_imaging_lesion_size():
    got = extract_findings("imaging_report", "3.4 cm spiculated mass in the right upper lobe.")
    by_key = {f["key"]: f for f in got}
    assert by_key["lesion_longest_mm"]["value"] == "34"


def test_extract_pathology_histology_and_nodes():
    text = (
        "CT-guided biopsy: adenocarcinoma. Station 7 node positive for malignancy. "
        "No distant metastatic disease identified."
    )
    got = {f["key"]: f for f in extract_findings("pathology_report", text)}
    assert got["histology"]["value"] == "adenocarcinoma"
    assert got["nodal_pathology"]["value"] == "station 7 positive"
    assert got["distant_metastasis"]["value"] == "documented_negative"


def test_extract_non_diagnostic_tissue():
    got = extract_findings("pathology_report", "Insufficient tissue; non-diagnostic specimen.")
    by_key = {f["key"]: f for f in got}
    assert by_key["tissue_adequacy"]["value"] == "non-diagnostic"


def test_extract_empty_text():
    assert extract_findings("imaging_report", "") == []


# --- ingest writes findings with provenance ---------------------------------


def _create_case():
    r = client.post(
        "/api/cases",
        json={
            "patient_ref": "F1",
            "intake": {
                "age": 66,
                "sex": "male",
                "reason_for_presentation": "Abnormal CT",
                "imaging": ["ct_chest"],
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def test_ingest_writes_findings_with_provenance():
    cid = _create_case()
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("ct.txt", b"3.4 cm spiculated RUL mass.", "text/plain")},
        data={"case_id": cid},
    )
    assert r.status_code == 201, r.text
    findings = client.get(f"/api/cases/{cid}/findings").json()["data"]["findings"]
    assert findings, "imaging report must produce findings"
    f = findings[0]
    assert f["source_doc"] == "ct.txt"
    assert f["origin"] == "ai"
    assert f["verification"] == "pending"
    assert f["confidence"] in {"high", "medium", "low"}
    assert f["case_id"] == cid


def test_finding_verification_transitions():
    cid = _create_case()
    client.post(
        "/api/documents/ingest",
        files={"file": ("ct.txt", b"3.4 cm mass.", "text/plain")},
        data={"case_id": cid},
    )
    fid = client.get(f"/api/cases/{cid}/findings").json()["data"]["findings"][0]["id"]

    r = client.post(f"/api/findings/{fid}/verify", json={"action": "accept"})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["verification"] == "accepted"
    assert isinstance(body["verified_by"], str), "who verified is recorded"

    r = client.post(f"/api/findings/{fid}/verify", json={"action": "reject"})
    assert r.json()["data"]["verification"] == "rejected"

    r = client.post(
        f"/api/findings/{fid}/verify",
        json={"action": "edit", "value": "21", "confidence": "high"},
    )
    body = r.json()["data"]
    assert body["value"] == "21"
    assert body["origin"] == "clinician", "edited values are clinician-sourced"
    assert body["verification"] == "accepted"

    r = client.post(f"/api/findings/{fid}/verify", json={"action": "unknown"})
    assert r.json()["data"]["verification"] == "unknown"


def test_verify_unknown_action_422():
    r = client.post("/api/findings/nope/verify", json={"action": "explode"})
    assert r.status_code == 422


def test_verify_missing_finding_404():
    r = client.post("/api/findings/does-not-exist/verify", json={"action": "accept"})
    assert r.status_code == 404


def test_assessment_after_ingest_uses_persisted_findings():
    cid = _create_case()
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("ct.txt", b"3.4 cm spiculated RUL mass.", "text/plain")},
        data={"case_id": cid},
    )
    assert r.status_code == 201, r.text
    data = client.get(f"/api/cases/{cid}/assessment").json()["data"]
    assert data["diagnostic_state"]["state"] == "malignancy_suspected"
    assert data["tnm"]["t"] == "cT2a"
    assert data["contradictions"] == []


def test_conflicting_evidence_forces_indeterminate_stage():
    cid = _create_case()
    for name, body in (
        ("ct.txt", b"3.4 cm spiculated RUL mass."),
        ("ct2.txt", b"Follow-up CT chest: lesion now measures 21 mm in the RUL."),
    ):
        r = client.post(
            "/api/documents/ingest",
            files={"file": (name, body, "text/plain")},
            data={"case_id": cid},
        )
        assert r.status_code == 201, r.text
    data = client.get(f"/api/cases/{cid}/assessment").json()["data"]
    assert data["diagnostic_state"]["state"] == "uncertain"
    assert len(data["contradictions"]) == 1
    assert data["tnm"]["determinable"] is False
    assert "indeterminate" in data["tnm"]["stage_group"].lower()


# --- contradictions ---------------------------------------------------------


def test_measurement_conflict_across_documents():
    findings = [
        {"key": "lesion_longest_mm", "value": "34", "source_doc": "ct1.txt",
         "verification": "accepted"},
        {"key": "lesion_longest_mm", "value": "21", "source_doc": "ct2.txt",
         "verification": "pending"},
    ]
    conflicts = detect_conflicts(findings)
    assert conflicts, "34mm vs 21mm must be flagged"
    c = conflicts[0]
    assert c["type"] == "measurement_conflict"
    assert {v["value"] for v in c["values"]} == {"34", "21"}


def test_histology_conflict_never_silently_resolved():
    findings = [
        {"key": "histology", "value": "adenocarcinoma", "source_doc": "biopsy.txt",
         "verification": "pending"},
        {"key": "histology", "value": "squamous cell carcinoma", "source_doc": "resection.txt",
         "verification": "pending"},
    ]
    conflicts = detect_conflicts(findings)
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "histology_conflict"
    assert len(conflicts[0]["values"]) == 2


def test_no_conflict_on_agreement_or_rejected():
    agree = [
        {"key": "lesion_longest_mm", "value": "34", "source_doc": "a", "verification": "accepted"},
        {"key": "lesion_longest_mm", "value": "34", "source_doc": "b", "verification": "pending"},
    ]
    assert detect_conflicts(agree) == []
    rejected = [
        {"key": "lesion_longest_mm", "value": "34", "source_doc": "a", "verification": "rejected"},
        {"key": "lesion_longest_mm", "value": "21", "source_doc": "b", "verification": "pending"},
    ]
    assert detect_conflicts(rejected) == [], "rejected evidence is not a conflict"
