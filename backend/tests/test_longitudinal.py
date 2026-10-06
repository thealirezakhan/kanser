"""Longitudinal evidence-first workflow: visits, documents, case states.

Examples A-E from the product spec must hold end to end.
"""

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.states import case_state

client = TestClient(app)


def _create(intake=None, notes=""):
    payload = {"patient_ref": "L1", "clinical_notes": notes}
    if intake is not None:
        payload["intake"] = intake
    r = client.post("/api/cases", json=payload)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


# --- visits -----------------------------------------------------------------


def test_case_create_auto_visit_1():
    cid = _create(
        {
            "age": 62,
            "sex": "male",
            "reason_for_presentation": "Persistent cough",
        }
    )
    data = client.get(f"/api/cases/{cid}/visits").json()["data"]
    assert len(data["visits"]) == 1
    v = data["visits"][0]
    assert v["visit_type"] == "initial_consultation"
    assert v["reason"] == "Persistent cough"
    assert v["visit_date"] <= str(date.today())


def test_add_visit_with_type_and_reason():
    cid = _create({"age": 62, "sex": "male", "reason_for_presentation": "Abnormal CT"})
    r = client.post(
        f"/api/cases/{cid}/visits",
        json={
            "visit_date": "2026-09-19",
            "visit_type": "imaging_review",
            "reason": "CT uploaded",
            "doctor": "dr_smith",
            "notes": "3.4 cm RUL lesion",
            "size_mm": 34.0,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    assert body["visit_type"] == "imaging_review"
    assert body["doctor"] == "dr_smith"
    visits = client.get(f"/api/cases/{cid}/visits").json()["data"]["visits"]
    assert len(visits) == 2, "auto visit 1 + new visit"
    review = [v for v in visits if v["visit_type"] == "imaging_review"]
    assert review and review[0]["doctor"] == "dr_smith"


def test_visit_type_enum_validated():
    cid = _create({"age": 62, "sex": "male", "reason_for_presentation": "Cough"})
    r = client.post(
        f"/api/cases/{cid}/visits",
        json={"visit_date": "2026-09-19", "visit_type": "party"},
    )
    assert r.status_code == 422


def test_document_record_attached_to_visit():
    import json

    cid = _create({"age": 62, "sex": "male", "reason_for_presentation": "Abnormal CT"})
    visits = client.get(f"/api/cases/{cid}/visits").json()["data"]["visits"]
    vid = visits[0]["id"]
    r = client.post(
        "/api/documents/ingest",
        files={"file": ("note.txt", b"cough for 3 months", "text/plain")},
        data={"case_id": cid, "visit_id": vid},
    )
    assert r.status_code == 201, r.text
    got = client.get(f"/api/cases/{cid}").json()["data"]
    docs = json.loads(got["metadata"]["documents"])
    assert docs[0]["visit_id"] == vid
    assert docs[0]["filename"] == "note.txt"
    assert docs[0]["sha256"]


def test_document_defaults_to_latest_visit():
    import json

    cid = _create({"age": 62, "sex": "male", "reason_for_presentation": "Cough"})
    client.post(
        "/api/documents/ingest",
        files={"file": ("labs.txt", b"Hb 13.2", "text/plain")},
        data={"case_id": cid},
    )
    visits = client.get(f"/api/cases/{cid}/visits").json()["data"]["visits"]
    got = client.get(f"/api/cases/{cid}").json()["data"]
    docs = json.loads(got["metadata"]["documents"])
    assert docs[0]["visit_id"] == visits[-1]["id"]


# --- diagnostic state machine (spec examples) -------------------------------


def test_example_a_symptoms_only():
    """No imaging -> insufficient evidence, system must not diagnose cancer."""
    s = case_state(
        {
            "modalities": [],
            "intake": {
                "age": 58,
                "sex": "male",
                "symptoms": [{"name": "cough", "state": "present"}],
            },
        },
        findings=[],
        contradictions=[],
    )
    assert s["state"] == "no_evidence"
    assert "insufficient" in s["label"].lower()


def test_example_b_cxr_opacity():
    s = case_state(
        {
            "modalities": ["cxr"],
            "clinical_notes": "Chest X-ray shows right upper lobe opacity.",
            "intake": {"age": 65, "sex": "male"},
        },
        findings=[],
        contradictions=[],
    )
    assert s["state"] == "abnormal_finding"


def test_example_c_ct_suspicious_no_tissue():
    s = case_state(
        {
            "modalities": ["ct"],
            "clinical_notes": "3.4 cm spiculated RUL lesion.",
            "intake": {"age": 70, "sex": "male"},
        },
        findings=[
            {"key": "lesion_longest_mm", "value": "34", "verification": "pending"},
        ],
        contradictions=[],
    )
    assert s["state"] == "malignancy_suspected"
    assert "cannot be confirmed" in s["explanation"].lower() or "imaging" in s[
        "explanation"
    ].lower()


def test_example_d_histology_confirmed_stage_pending():
    s = case_state(
        {
            "modalities": ["ct", "pathology"],
            "intake": {
                "age": 68,
                "sex": "male",
                "tissue_status": "histology_available",
                "histology": "adenocarcinoma",
            },
        },
        findings=[{"key": "histology", "value": "adenocarcinoma", "verification": "pending"}],
        contradictions=[],
    )
    assert s["state"] == "histology_confirmed"


def test_example_e_full_staging_establishes_stage():
    s = case_state(
        {
            "modalities": ["ct", "pathology"],
            "metadata": {"imaging_findings": '{"max_mm": 15}'},
            "intake": {
                "age": 68,
                "sex": "male",
                "tissue_status": "histology_available",
                "histology": "adenocarcinoma",
                "mediastinal": "assessed",
            },
        },
        findings=[
            {"key": "lesion_longest_mm", "value": "15", "verification": "accepted"},
            {"key": "histology", "value": "adenocarcinoma", "verification": "accepted"},
            {"key": "nodal_pathology", "value": "station 7 negative", "verification": "accepted"},
            {
                "key": "distant_metastasis",
                "value": "documented_negative",
                "verification": "accepted",
            },
        ],
        contradictions=[],
    )
    assert s["state"] == "stage_established"


def test_tissue_pending_state():
    s = case_state(
        {
            "modalities": ["ct"],
            "intake": {"age": 70, "sex": "male", "tissue_status": "biopsy_pending"},
        },
        findings=[{"key": "lesion_longest_mm", "value": "34", "verification": "pending"}],
        contradictions=[],
    )
    assert s["state"] == "tissue_pending"


def test_non_diagnostic_biopsy_state():
    s = case_state(
        {
            "modalities": ["ct", "pathology"],
            "intake": {"age": 70, "sex": "male", "tissue_status": "biopsy_performed"},
        },
        findings=[{"key": "tissue_adequacy", "value": "non-diagnostic", "verification": "pending"}],
        contradictions=[],
    )
    assert s["state"] == "non_diagnostic"


def test_contradictions_force_uncertain_state():
    s = case_state(
        {
            "modalities": ["ct", "pathology"],
            "intake": {
                "age": 70,
                "sex": "male",
                "tissue_status": "histology_available",
                "histology": "adenocarcinoma",
            },
        },
        findings=[],
        contradictions=[{"type": "measurement_conflict"}],
    )
    assert s["state"] == "uncertain"


def test_primary_uncertain_when_metastatic_pattern():
    s = case_state(
        {
            "modalities": ["ct", "pathology"],
            "intake": {"age": 70, "sex": "male", "tissue_status": "histology_available"},
        },
        findings=[
            {"key": "histology", "value": "adenocarcinoma", "verification": "pending"},
            {
                "key": "primary_origin",
                "value": "other_primary_suspected",
                "verification": "pending",
            },
        ],
        contradictions=[],
    )
    assert s["state"] == "primary_uncertain"


def test_recurrence_encounter_state():
    s = case_state(
        {
            "modalities": ["ct"],
            "intake": {"age": 70, "sex": "male", "encounter": "recurrence"},
        },
        findings=[],
        contradictions=[],
    )
    assert s["state"] == "recurrence_eval"


# --- assessment endpoint carries the longitudinal bundle --------------------


def test_assessment_endpoint_has_state_tnm_conflicts():
    r = client.post(
        "/api/cases",
        json={
            "patient_ref": "A1",
            "intake": {
                "age": 62,
                "sex": "male",
                "reason_for_presentation": "Abnormal CT",
            },
        },
    )
    cid = r.json()["data"]["id"]
    data = client.get(f"/api/cases/{cid}/assessment").json()["data"]
    assert set(data) >= {
        "pathway",
        "readiness",
        "routing",
        "agents_skipped",
        "must_not_infer",
        "diagnostic_state",
        "tnm",
        "contradictions",
    }
    assert data["diagnostic_state"]["state"] == "no_evidence"
    assert data["tnm"]["determinable"] is False
    assert data["tnm"]["stage_group"] == "Stage indeterminate - insufficient evidence"
