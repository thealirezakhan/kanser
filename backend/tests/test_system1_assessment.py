"""System 1 clinical orchestration: pathway, gates, why-not-infer rationale."""

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import CaseInput, Intake
from app.system1 import assess_case, pathway_for

client = TestClient(app)


def _case(intake: Intake | None = None, modalities=None, notes=""):
    return CaseInput(
        patient_ref="s1",
        modalities=modalities or [],
        clinical_notes=notes,
        intake=intake,
    )


def test_pathway_mapping():
    assert pathway_for("new_suspected") == "diagnostic"
    assert pathway_for("staging") == "staging"
    assert pathway_for("treatment_planning") == "treatment"
    assert pathway_for("surveillance") == "surveillance"
    assert pathway_for("nonsense") == "diagnostic"


def test_assessment_shape_with_no_data():
    a = assess_case(_case())
    assert a.pathway == "diagnostic"
    assert a.readiness["system_status"] == "NOT_READY"
    assert a.routing.risk_grade in {"low", "medium", "high"}
    assert "radiology" in a.agents_skipped
    assert "imaging" in a.agents_skipped["radiology"]
    joined = " ".join(a.must_not_infer)
    assert "PET/CT" in joined
    assert "histology" in joined.lower()
    assert "ECOG" in joined
    assert "brain" not in joined.lower(), "brain imaging is not intake scope"


def test_complete_case_clears_gates_and_inference_limits():
    intake = Intake(
        age=62,
        sex="male",
        reason_for_presentation="Staging after biopsy",
        encounter="staging",
        smoking_status="former",
        symptoms=[{"name": "cough", "state": "present"}],
        imaging=["ct_chest", "pet_ct"],
        prior_imaging="assessed",
        tissue_status="histology_available",
        histology="adenocarcinoma",
        mediastinal="assessed",
        molecular_status="complete",
        ecog=1,
        fev1_pct=70,
    )
    a = assess_case(_case(intake, modalities=["ct", "pathology", "genomics", "notes"]))
    assert a.pathway == "staging"
    assert a.readiness["system_status"] == "READY_FOR_TREATMENT_PLANNING"
    assert a.readiness["uncertainty_flags"] == []
    assert a.must_not_infer == []
    assert "radiology" in a.routing.activated
    assert "radiology" not in a.agents_skipped


def test_assessed_not_performed_blocks_m_stage_with_reason():
    intake = Intake(
        age=70,
        sex="female",
        reason_for_presentation="Staging workup",
        encounter="staging",
        imaging=["ct_chest"],
        not_performed=["pet_ct"],
    )
    a = assess_case(_case(intake, modalities=["ct"]))
    pet_item = next(
        i
        for i in a.readiness["pathways"]["staging"]["items"]
        if i["key"] == "pet_ct"
    )
    assert pet_item["reason"] == "assessed: not performed"
    assert any("PET/CT" in w for w in a.must_not_infer)


def test_endpoint_assessment():
    cid = client.post("/api/cases", json={"patient_ref": "a1"}).json()["data"]["id"]
    r = client.get(f"/api/cases/{cid}/assessment")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data) == {
        "pathway",
        "readiness",
        "routing",
        "agents_skipped",
        "must_not_infer",
        "diagnostic_state",
        "tnm",
        "contradictions",
    }
    assert set(data["routing"]) >= {"activated", "dropped", "risk_grade", "priority"}


def test_endpoint_assessment_404():
    assert client.get("/api/cases/nope/assessment").status_code == 404
