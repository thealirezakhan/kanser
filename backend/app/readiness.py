"""Clinical Completeness Engine: deterministic workup-readiness scoring.

No LLM. Distinguishes unknown / not performed / not applicable — a missing
PET/CT is not a negative PET/CT, and that difference propagates to gates.
"""

from typing import Any

_COMPLETE_TISSUE = {
    "biopsy_performed",
    "cytology_only",
    "histology_available",
    "surgical_specimen",
}
_HISTOLOGY = {"histology_available", "surgical_specimen"}
_PENDING_TISSUE = {"biopsy_planned", "biopsy_pending"}
_IMAGING_KEYS = {"ct_chest", "pet_ct"}
_PRIOR_REQUIRED = {"recurrence", "treatment_response", "second_opinion"}

_RECOMMEND = {
    "presentation": "Reason for presentation",
    "clinical_history": "Age and sex",
    "smoking_history": "Smoking history",
    "symptoms": "Symptom assessment",
    "imaging": "Chest imaging (CT)",
    "tissue_diagnosis": "Tissue biopsy",
    "histology": "Histopathology report",
    "ct_chest": "Cross-sectional chest imaging (CT)",
    "pet_ct": "PET/CT",
    "mediastinal_assessment": "Mediastinal nodal assessment (EBUS)",
    "ecog": "ECOG performance status",
    "pulmonary_function": "Pulmonary function tests (FEV1/DLCO)",
    "molecular_profile": "Molecular profiling (NGS)",
    "prior_treatment": "Prior treatment history",
}

_QUESTIONS = {
    "presentation": "Why is this patient presenting?",
    "clinical_history": "How old is the patient and what is their sex?",
    "smoking_history": "What is the smoking history?",
    "symptoms": "Which symptoms are present?",
    "imaging": "Is cross-sectional chest imaging available?",
    "tissue_diagnosis": "Has tissue been sampled for diagnosis?",
    "histology": "What is the histologic diagnosis?",
    "ct_chest": "Is a diagnostic chest CT available?",
    "pet_ct": "Is whole-body metabolic staging (PET/CT) available?",
    "mediastinal_assessment": "Have the mediastinal nodes been sampled?",
    "ecog": "What is the performance status?",
    "pulmonary_function": "Are PFTs available to assess surgical risk?",
    "molecular_profile": "Is a molecular profile available?",
    "prior_treatment": "Has prior cancer treatment occurred?",
}

_PRIORITY = {"diagnostic": "routine", "staging": "when_indicated", "treatment": "conditional"}


def _item(key: str, label: str, status: str, reason: str) -> dict:
    return {"key": key, "label": label, "status": status, "reason": reason}


def _study(key: str, label: str, present: bool, not_performed: set[str]) -> dict:
    if present:
        return _item(key, label, "complete", f"{label} available")
    if key in not_performed or label in not_performed:
        return _item(key, label, "missing", "assessed: not performed")
    return _item(key, label, "missing", f"{label} not yet assessed")


def _histology(tissue: str, label: str) -> dict:
    if tissue in _HISTOLOGY:
        return _item("histology", label, "complete", "histology available")
    if tissue in _COMPLETE_TISSUE | _PENDING_TISSUE:
        return _item("histology", label, "pending", "histology not yet available")
    return _item("histology", label, "missing", "histology missing")


def _pathway_diagnostic(intake: dict, mods: set[str], imaging: set[str]) -> list[dict]:
    has_history = intake.get("age") is not None and bool(intake.get("sex"))
    items = [
        _item(
            "clinical_history",
            "Clinical history",
            "complete" if has_history else "missing",
            "age and sex recorded" if has_history else "age/sex not recorded",
        ),
    ]
    has_reason = bool(str(intake.get("reason_for_presentation", "")).strip())
    items.append(
        _item(
            "presentation",
            "Reason for presentation",
            "complete" if has_reason else "missing",
            "reason recorded" if has_reason else "reason for presentation not recorded",
        )
    )
    smoking = intake.get("smoking_status", "unknown") != "unknown"
    items.append(
        _item(
            "smoking_history",
            "Smoking history",
            "complete" if smoking else "missing",
            "smoking status recorded" if smoking else "smoking not yet assessed",
        )
    )
    assessed = any(s.get("state") in {"present", "absent"} for s in intake.get("symptoms", []))
    if assessed:
        items.append(_item("symptoms", "Symptoms", "complete", "symptoms assessed"))
    else:
        items.append(_item("symptoms", "Symptoms", "pending", "symptoms not yet assessed"))
    not_done = set(intake.get("not_performed", []))
    has_img = bool(mods & {"ct", "cxr"}) or bool(imaging & _IMAGING_KEYS)
    items.append(_study("imaging", "Cross-sectional imaging", has_img, not_done))
    tissue = intake.get("tissue_status", "unknown")
    if tissue in _COMPLETE_TISSUE:
        status, reason = "complete", f"tissue status: {tissue}"
    elif tissue in _PENDING_TISSUE:
        status, reason = "pending", f"tissue status: {tissue}"
    elif tissue == "no_tissue":
        status, reason = "missing", "no tissue obtained"
    else:
        status, reason = "missing", "tissue status not yet assessed"
    items.append(_item("tissue_diagnosis", "Tissue diagnosis", status, reason))
    items.append(_histology(tissue, "Histology"))
    return items


def _pathway_staging(intake: dict, mods: set[str], imaging: set[str]) -> list[dict]:
    not_done = set(intake.get("not_performed", []))
    has_ct = "ct" in mods or bool(imaging & {"ct_chest", "pet_ct"})
    items = [
        _study("ct_chest", "CT chest", has_ct, not_done),
        _study("pet_ct", "PET/CT", "pet_ct" in imaging, not_done),
    ]
    med = intake.get("mediastinal", "unknown")
    if med == "assessed":
        m = _item(
            "mediastinal_assessment", "Mediastinal assessment", "complete", "assessment available"
        )
    elif med == "not_performed":
        m = _item(
            "mediastinal_assessment", "Mediastinal assessment", "missing", "assessed: not performed"
        )
    elif med == "not_applicable":
        m = _item(
            "mediastinal_assessment", "Mediastinal assessment", "not_applicable", "not applicable"
        )
    else:
        m = _item("mediastinal_assessment", "Mediastinal assessment", "missing", "not yet assessed")
    items.append(m)
    items.append(_histology(intake.get("tissue_status", "unknown"), "Histology"))
    return items


def _pathway_treatment(intake: dict) -> list[dict]:
    items = []
    if intake.get("ecog") is not None:
        items.append(_item("ecog", "ECOG performance status", "complete", "ECOG recorded"))
    else:
        items.append(_item("ecog", "ECOG performance status", "missing", "ECOG not recorded"))
    has_pft = intake.get("fev1_pct") is not None or intake.get("dlco_pct") is not None
    if has_pft:
        items.append(
            _item("pulmonary_function", "Pulmonary function", "complete", "PFT values recorded")
        )
    else:
        items.append(
            _item("pulmonary_function", "Pulmonary function", "missing", "PFT not recorded")
        )
    mol = intake.get("molecular_status", "unknown")
    if mol == "complete":
        m = _item(
            "molecular_profile", "Molecular profile", "complete", "molecular testing complete"
        )
    elif mol in {"ordered", "pending", "partial"}:
        m = _item("molecular_profile", "Molecular profile", "pending", f"molecular testing {mol}")
    elif mol == "not_ordered":
        m = _item("molecular_profile", "Molecular profile", "missing", "testing not ordered")
    else:
        m = _item("molecular_profile", "Molecular profile", "missing", "not yet assessed")
    items.append(m)
    items.append(_histology(intake.get("tissue_status", "unknown"), "Histology"))
    encounter = intake.get("encounter", "new_suspected")
    if encounter not in _PRIOR_REQUIRED:
        items.append(
            _item("prior_treatment", "Prior treatment", "not_applicable", "not applicable here")
        )
    elif intake.get("prior_cancer"):
        items.append(_item("prior_treatment", "Prior treatment", "complete", "history recorded"))
    else:
        items.append(_item("prior_treatment", "Prior treatment", "missing", "history not recorded"))
    return items


def _score(items: list[dict]) -> tuple[int, bool]:
    applicable = [i for i in items if i["status"] != "not_applicable"]
    if not applicable:
        return 100, True
    done = sum(1 for i in applicable if i["status"] == "complete")
    return round(100 * done / len(applicable)), all(i["status"] == "complete" for i in applicable)


_PENALTY = {"complete": 0.0, "not_applicable": 0.0, "pending": 0.05, "missing": 0.1}


def _confidence(items: list[dict]) -> float:
    """Soft uncertainty penalty: gaps lower confidence, never flip readiness."""
    return round(max(0.2, 1.0 - sum(_PENALTY[i["status"]] for i in items)), 2)


def _status_tiers(pathways: dict) -> str:
    if pathways["treatment"]["ready"]:
        return "READY_FOR_TREATMENT_PLANNING"
    if pathways["staging"]["ready"]:
        return "READY_FOR_STAGING"
    if pathways["diagnostic"]["ready"]:
        return "READY_FOR_DIAGNOSIS"
    return "NOT_READY"


def evaluate(intake: dict, modalities: list[str]) -> dict:
    """Score diagnostic / staging / treatment readiness from intake + uploaded data.

    Diagnostic and staging gate on cross-sectional imaging only — they run with
    what exists and report confidence + uncertainty flags. Treatment gates on
    ECOG, PFT, histology, and molecular completeness.
    """
    mods = set(modalities)
    imaging = set(intake.get("imaging", []))
    builders = {
        "diagnostic": lambda: _pathway_diagnostic(intake, mods, imaging),
        "staging": lambda: _pathway_staging(intake, mods, imaging),
        "treatment": lambda: _pathway_treatment(intake),
    }
    pathways: dict[str, Any] = {}
    recommended: list[str] = []
    structured: list[dict] = []
    seen_rec: set[str] = set()
    flags: dict[str, str] = {}
    _scope = {"diagnostic": "Diagnostic", "staging": "Staging", "treatment": "Treatment"}
    for name, build in builders.items():
        items = build()
        score, complete = _score(items)
        pathways[name] = {
            "score": score,
            "ready": complete,
            "confidence": _confidence(items),
            "items": items,
        }
        for i in items:
            rec = _RECOMMEND.get(i["key"])
            if i["status"] in {"missing", "pending"} and rec and rec not in seen_rec:
                seen_rec.add(rec)
                recommended.append(f"{_scope[name]}: {rec}")
                structured.append(
                    {
                        "test": rec,
                        "question": _QUESTIONS.get(i["key"], f"{i['label']} missing?"),
                        "why": f"{i['label']}: {i['reason']}",
                        "priority": _PRIORITY[name],
                        "pathway": _scope[name],
                        "conditional": name != "diagnostic",
                    }
                )
            if i["status"] in {"missing", "pending"} and i["key"] not in flags:
                flags[i["key"]] = (
                    f"Clinical data gap ({_scope[name]}): {i['label']} - {i['reason']}"
                )
    # Tiered gates: radiological pathways run on imaging alone
    has_ct = bool(mods & {"ct", "cxr"}) or bool(imaging & {"ct_chest", "pet_ct"})
    pathways["diagnostic"]["ready"] = has_ct
    pathways["staging"]["ready"] = has_ct
    # treatment keeps its full-completeness gate (ECOG + PFT + histology + molecular)
    return {
        "system_status": _status_tiers(pathways),
        "pathways": pathways,
        "recommended_tests": recommended,
        "recommendations": structured,
        "uncertainty_flags": [
            {"key": k, "message": m} for k, m in sorted(flags.items(), key=lambda x: x[0])
        ],
    }
