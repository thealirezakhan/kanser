"""Clinical case intake: minimum viable creation, optional evidence fields.

Evidence-first contract: reason for presentation + age + sex create a case.
Imaging, tissue, molecular, staging are NEVER required at creation.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create(payload: dict):
    return client.post("/api/cases", json=payload)


def test_legacy_case_without_intake_still_accepted():
    r = _create({"patient_ref": "legacy-1"})
    assert r.status_code == 201
    case_id = r.json()["data"]["id"]
    got = client.get(f"/api/cases/{case_id}").json()["data"]
    assert got["intake"] == {}


def test_intake_requires_age_and_sex():
    r = _create({"patient_ref": "p1", "intake": {"sex": "male"}})
    assert r.status_code == 422
    r = _create({"patient_ref": "p1", "intake": {"age": 62}})
    assert r.status_code == 422


def test_intake_requires_reason_for_presentation():
    r = _create({"patient_ref": "p1", "intake": {"age": 62, "sex": "male"}})
    assert r.status_code == 422, "reason for presentation is mandatory at creation"
    r = _create(
        {
            "patient_ref": "p1",
            "intake": {"age": 62, "sex": "male", "reason_for_presentation": "Persistent cough"},
        }
    )
    assert r.status_code == 201, r.text


def test_minimum_viable_case_needs_no_imaging():
    """Example A: symptoms only — case must be creatable, state will be no_evidence."""
    r = _create(
        {
            "patient_ref": "min-1",
            "clinical_notes": "58M smoker, persistent cough. No imaging yet.",
            "intake": {
                "age": 58,
                "sex": "male",
                "reason_for_presentation": "Persistent cough",
                "smoking_status": "current",
                "symptoms": [{"name": "cough", "state": "present"}],
            },
        }
    )
    assert r.status_code == 201, r.text
    got = client.get(f"/api/cases/{r.json()['data']['id']}").json()["data"]
    assert got["intake"]["imaging"] == []


def test_sex_unknown_allowed():
    r = _create(
        {
            "patient_ref": "p6",
            "intake": {
                "age": 70,
                "sex": "unknown",
                "reason_for_presentation": "Abnormal chest X-ray",
            },
        }
    )
    assert r.status_code == 201, r.text


def test_intake_valid_roundtrip():
    intake = {
        "age": 62,
        "sex": "male",
        "reason_for_presentation": "Abnormal CT",
        "encounter": "new_suspected",
        "smoking_status": "former",
        "pack_years": 35,
        "symptoms": [{"name": "cough", "state": "present", "duration": "3 mo"}],
        "imaging": ["ct_chest"],
        "tissue_status": "biopsy_pending",
        "molecular_status": "pending",
        "biomarkers": [{"gene": "EGFR", "result": "pending"}],
        "ecog": 1,
    }
    r = _create({"patient_ref": "p2", "intake": intake})
    assert r.status_code == 201, r.text
    got = client.get(f"/api/cases/{r.json()['data']['id']}").json()["data"]
    assert got["intake"]["age"] == 62
    assert got["intake"]["symptoms"][0]["state"] == "present"
    assert got["intake"]["biomarkers"][0]["gene"] == "EGFR"
    assert got["intake"]["ecog"] == 1


def test_intake_extra_field_forbidden():
    r = _create(
        {
            "patient_ref": "p3",
            "intake": {
                "age": 50,
                "sex": "female",
                "reason_for_presentation": "Cough",
                "bogus": 1,
            },
        }
    )
    assert r.status_code == 422


def test_intake_enum_validation():
    r = _create(
        {
            "patient_ref": "p4",
            "intake": {
                "age": 50,
                "sex": "female",
                "reason_for_presentation": "Cough",
                "encounter": "party",
            },
        }
    )
    assert r.status_code == 422
    r = _create(
        {
            "patient_ref": "p4",
            "intake": {
                "age": 50,
                "sex": "female",
                "reason_for_presentation": "Cough",
                "ecog": 9,
            },
        }
    )
    assert r.status_code == 422


def test_intake_imaging_optional_but_values_restricted():
    r = _create(
        {
            "patient_ref": "px",
            "intake": {"age": 50, "sex": "male", "reason_for_presentation": "Cough"},
        }
    )
    assert r.status_code == 201, "empty imaging is valid at creation"
    for study in ("brain_mri", "brain_ct", "other_mri", "cxr"):
        r = _create(
            {
                "patient_ref": "px",
                "intake": {
                    "age": 50,
                    "sex": "male",
                    "reason_for_presentation": "Cough",
                    "imaging": ["ct_chest", study],
                },
            }
        )
        assert r.status_code == 422, f"{study} must not be an allowed intake field"


def test_intake_age_bounds():
    r = _create({"patient_ref": "p5", "intake": {"age": -1, "sex": "male"}})
    assert r.status_code == 422
    r = _create({"patient_ref": "p5", "intake": {"age": 131, "sex": "male"}})
    assert r.status_code == 422
