"""Clinical Completeness Engine: tiered readiness, soft uncertainty flags.

Gate rules (revised):
- Diagnostic: never blocked once cross-sectional imaging exists (radiological run).
- Staging: runs partially on CT/PET; missing mediastinal = gap, not block.
- Treatment: blocked until ECOG + PFT + histology + molecular are populated.
Missing smoking/pending biopsy etc. are Clinical Data Gaps (uncertainty flags),
never hard errors. Recommendations and flags are scoped per pathway so a
diagnosis-phase case never reads staging/treatment items as diagnosis requirements.
Brain imaging is not part of lung cancer diagnosis intake at all.
"""

from app.readiness import evaluate

FULL = {
    "age": 62,
    "sex": "male",
    "reason_for_presentation": "Abnormal CT screening",
    "encounter": "newly_diagnosed",
    "smoking_status": "former",
    "pack_years": 35,
    "symptoms": [{"name": "cough", "state": "present"}],
    "imaging": ["ct_chest", "pet_ct"],
    "prior_imaging": "assessed",
    "tissue_status": "histology_available",
    "histology": "adenocarcinoma",
    "mediastinal": "assessed",
    "molecular_status": "complete",
    "biomarkers": [{"gene": "EGFR", "result": "exon 19 del"}],
    "ecog": 1,
    "fev1_pct": 72,
    "dlco_pct": 68,
}


def _item(report: dict, pathway: str, key: str) -> dict:
    items = report["pathways"][pathway]["items"]
    return next(i for i in items if i["key"] == key)


def test_empty_input_not_ready():
    r = evaluate({}, [])
    assert r["system_status"] == "NOT_READY"
    assert r["pathways"]["diagnostic"]["ready"] is False
    assert r["pathways"]["staging"]["ready"] is False
    assert r["pathways"]["treatment"]["ready"] is False
    assert any("PET/CT" in t for t in r["recommended_tests"]) or any(
        "ECOG performance status" in t for t in r["recommended_tests"]
    )
    assert len(r["uncertainty_flags"]) > 0


def test_recommendations_scoped_by_pathway():
    r = evaluate({}, [])
    assert len(r["recommended_tests"]) > 0
    prefixes = {t.split(":")[0] for t in r["recommended_tests"]}
    assert prefixes <= {"Diagnostic", "Staging", "Treatment"}, prefixes
    assert prefixes & {"Diagnostic", "Staging"}, "each phase shows its own scope"
    for f in r["uncertainty_flags"]:
        assert f["message"].startswith("Clinical data gap ("), f["message"]
        assert any(
            p in f["message"] for p in ("(Diagnostic)", "(Staging)", "(Treatment)")
        ), f["message"]


def test_diagnosis_phase_scoped_not_misleading():
    """Staging/treatment items must read as their own phase — and brain imaging
    must not appear anywhere: it is not part of lung cancer diagnosis intake."""
    r = evaluate({"age": 62, "sex": "male", "imaging": ["ct_chest"]}, ["ct"])
    assert r["pathways"]["diagnostic"]["ready"] is True
    assert not any("Brain" in t for t in r["recommended_tests"])
    assert not any(f["key"] == "brain_imaging" for f in r["uncertainty_flags"])
    ecog = [t for t in r["recommended_tests"] if "ECOG" in t]
    assert ecog == ["Treatment: ECOG performance status"]


def test_brain_imaging_removed_from_staging_items():
    r = evaluate({"age": 62, "sex": "male", "imaging": ["ct_chest", "pet_ct"]}, ["ct", "pet_ct"])
    keys = {i["key"] for i in r["pathways"]["staging"]["items"]}
    assert keys == {"ct_chest", "pet_ct", "mediastinal_assessment", "histology"}


def test_full_intake_ready_everywhere():
    r = evaluate(FULL, ["ct", "pathology", "genomics", "labs", "notes"])
    for p in ("diagnostic", "staging", "treatment"):
        assert r["pathways"][p]["ready"] is True, p
        assert r["pathways"][p]["score"] == 100, p
        assert r["pathways"][p]["confidence"] == 1.0
    assert r["system_status"] == "READY_FOR_TREATMENT_PLANNING"
    assert r["recommended_tests"] == []
    assert r["uncertainty_flags"] == []


def test_diagnostic_runs_with_ct_only_no_tissue():
    intake = {"age": 62, "sex": "male", "imaging": ["ct_chest"]}
    r = evaluate(intake, ["ct"])
    dg = r["pathways"]["diagnostic"]
    assert dg["ready"] is True, "CT exists -> diagnostic must not block"
    assert 0 < dg["confidence"] < 1, "gaps reduce confidence, not readiness"
    st = r["pathways"]["staging"]
    assert st["ready"] is True, "staging runs partially on CT"
    assert r["pathways"]["treatment"]["ready"] is False
    assert r["system_status"] == "READY_FOR_STAGING"
    gap_keys = {f["key"] for f in r["uncertainty_flags"]}
    assert "histology" in gap_keys
    assert "ecog" in gap_keys
    # pending tissue is a gap, not an error
    assert _item(r, "diagnostic", "tissue_diagnosis")["status"] == "missing"


def test_missing_age_sex_is_gap_not_diagnostic_block():
    intake = {k: v for k, v in FULL.items() if k not in ("age", "sex")}
    r = evaluate(intake, ["ct"])
    item = _item(r, "diagnostic", "clinical_history")
    assert item["status"] == "missing"
    assert r["pathways"]["diagnostic"]["ready"] is True
    assert any(f["key"] == "clinical_history" for f in r["uncertainty_flags"])


def test_unknown_vs_not_performed_reasons_differ():
    base = {k: v for k, v in FULL.items() if k != "pet_ct"}
    base["imaging"] = ["ct_chest"]

    r_unknown = evaluate(base, ["ct"])
    r_notdone = evaluate({**base, "not_performed": ["pet_ct"]}, ["ct"])

    item_u = _item(r_unknown, "staging", "pet_ct")
    item_n = _item(r_notdone, "staging", "pet_ct")
    assert item_u["status"] == item_n["status"] == "missing"
    assert item_u["reason"] != item_n["reason"]
    assert "not performed" in item_n["reason"].lower()
    assert "not yet assessed" in item_u["reason"].lower()
    # CT exists, so staging still runs (incomplete), it is not blocked
    assert r_unknown["pathways"]["staging"]["ready"] is True
    assert r_notdone["pathways"]["staging"]["ready"] is True


def test_not_applicable_excluded_from_score():
    intake = {**FULL, "encounter": "new_suspected", "prior_cancer": False}
    r = evaluate(intake, ["ct", "pathology", "genomics", "labs"])
    item = _item(r, "treatment", "prior_treatment")
    assert item["status"] == "not_applicable"
    assert r["pathways"]["treatment"]["score"] == 100
    assert r["pathways"]["treatment"]["ready"] is True


def test_pending_biopsy_gaps_diagnostic_but_blocks_treatment():
    intake = {**FULL, "tissue_status": "biopsy_pending"}
    r = evaluate(intake, ["ct"])
    assert _item(r, "diagnostic", "tissue_diagnosis")["status"] == "pending"
    assert r["pathways"]["diagnostic"]["ready"] is True, "radiological run allowed"
    assert r["pathways"]["treatment"]["ready"] is False, "histology gates treatment"
    assert any("Tissue biopsy" in t for t in r["recommended_tests"])
    assert any(f["key"] == "histology" for f in r["uncertainty_flags"])


def test_molecular_pending_blocks_treatment_only():
    intake = {**FULL, "molecular_status": "pending"}
    r = evaluate(intake, ["ct", "pathology", "genomics", "labs"])
    assert r["pathways"]["diagnostic"]["ready"] is True
    assert r["pathways"]["staging"]["ready"] is True
    assert r["pathways"]["treatment"]["ready"] is False
    assert _item(r, "treatment", "molecular_profile")["status"] == "pending"
    assert any("Molecular profiling (NGS)" in t for t in r["recommended_tests"])


def test_treatment_gate_requires_each_blocker():
    for overrides in (
        {"ecog": None},
        {"fev1_pct": None, "dlco_pct": None},
        {"molecular_status": "pending"},
        {"tissue_status": "biopsy_performed"},
    ):
        intake = {**FULL, **overrides}
        r = evaluate(intake, ["ct", "pathology", "genomics", "labs"])
        label = "/".join(overrides)
        assert r["pathways"]["treatment"]["ready"] is False, label
        assert r["pathways"]["diagnostic"]["ready"] is True, label


def test_uncertainty_flags_deduped_across_pathways():
    r = evaluate({}, [])
    keys = [f["key"] for f in r["uncertainty_flags"]]
    assert len(keys) == len(set(keys)), "histology gap repeats in 3 pathways"
    for flag in r["uncertainty_flags"]:
        assert set(flag) == {"key", "message"}
        assert flag["message"]


def test_structured_recommendations_answer_why():
    """Each rec names the test, the clinical question, and its phase priority."""
    r = evaluate({}, [])
    assert r["recommendations"], "empty intake must recommend next investigations"
    for rec in r["recommendations"]:
        assert set(rec) == {"test", "question", "why", "priority", "pathway", "conditional"}
        assert rec["pathway"] in {"Diagnostic", "Staging", "Treatment"}
        assert rec["priority"] in {"routine", "when_indicated", "conditional"}
        assert rec["question"].rstrip().endswith("?"), rec["question"]
        assert rec["why"]
    # diagnosis phase first, conditional phases marked
    assert any(rec["pathway"] == "Diagnostic" for rec in r["recommendations"])
    assert all(rec["conditional"] is True for rec in r["recommendations"]
               if rec["pathway"] == "Treatment")


def test_missing_reason_is_gap():
    r = evaluate({"age": 62, "sex": "male", "imaging": ["ct_chest"]}, ["ct"])
    assert any(f["key"] == "presentation" for f in r["uncertainty_flags"])
    assert any(
        "Reason for presentation" in t for t in r["recommended_tests"]
    )


def test_report_shape():
    r = evaluate({}, [])
    assert set(r) == {
        "system_status",
        "pathways",
        "recommended_tests",
        "recommendations",
        "uncertainty_flags",
    }
    for p in ("diagnostic", "staging", "treatment"):
        pw = r["pathways"][p]
        assert set(pw) == {"score", "ready", "confidence", "items"}
        assert 0 < pw["confidence"] <= 1
        for item in pw["items"]:
            assert set(item) == {"key", "label", "status", "reason"}
            assert item["status"] in {"complete", "pending", "missing", "not_applicable"}
