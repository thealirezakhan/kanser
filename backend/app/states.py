"""Longitudinal diagnostic state machine (evidence-first).

The state reflects only documented evidence. Missing evidence yields an
explicit unknown/indeterminate state — never a cancer diagnosis, never a
silent negative. Contradictions win: state becomes 'uncertain' until a
clinician resolves them.
"""

import re

from app.tnm import stage_case

_SUSPICIOUS = re.compile(
    r"spiculat|suspicious|mass|nodule|malignan|hypermetabol|lesion", re.I
)
_MALIGNANCY = re.compile(r"carcinoma|carcinoma|malignan|tumor|tumour|neoplasm", re.I)
_PENDING_TISSUE = {"biopsy_planned", "biopsy_pending", "biopsy_performed"}
_HISTOLOGY_TISSUE = {"histology_available", "surgical_specimen"}


def _state(key: str, label: str, explanation: str) -> dict:
    return {"state": key, "label": label, "explanation": explanation}


def _active(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("verification") != "rejected"]


def _values(findings: list[dict], key: str) -> list[str]:
    return [str(f.get("value", "")) for f in findings if f.get("key") == key]


def _has_imaging(case: dict, intake: dict) -> bool:
    return bool(set(case.get("modalities", [])) & {"ct", "cxr"}) or bool(
        set(intake.get("imaging", [])) & {"ct_chest", "pet_ct"}
    )


def _staging_activity(case: dict, intake: dict, findings: list[dict]) -> bool:
    return (
        intake.get("mediastinal") == "assessed"
        or "pet_ct" in set(intake.get("imaging", []))
        or bool(_values(findings, "nodal_pathology"))
    )


def case_state(case: dict, findings: list[dict], contradictions: list[dict]) -> dict:
    """Map case + findings + contradictions to the longitudinal case state."""
    if contradictions:
        return _state(
            "uncertain",
            "Conflicting evidence",
            "Contradictory evidence requires clinician resolution - "
            "the system will not choose a side silently.",
        )
    intake = case.get("intake") or {}
    active = _active(findings)
    encounter = intake.get("encounter", "new_suspected")
    if encounter in {"recurrence", "treatment_response"}:
        return _state(
            "recurrence_eval",
            "Recurrence / progression evaluation",
            "Encounter marked for recurrence or treatment-response evaluation.",
        )
    if "non-diagnostic" in _values(active, "tissue_adequacy"):
        return _state(
            "non_diagnostic",
            "Non-diagnostic tissue sample",
            "Biopsy result was non-diagnostic - tissue sampling must be repeated "
            "before any malignancy can be confirmed.",
        )
    histology = intake.get("histology") or ""
    if not histology:
        histology_hits = [v for v in _values(active, "histology") if v]
        histology = histology_hits[-1] if histology_hits else ""
    tissue = intake.get("tissue_status", "unknown")
    if histology and (tissue in _HISTOLOGY_TISSUE or _values(active, "histology")):
        if _values(active, "primary_origin"):
            return _state(
                "primary_uncertain",
                "Primary site uncertain",
                "Tissue confirms malignancy but the primary origin is not established.",
            )
        tnm = stage_case(case, active)
        if tnm["determinable"]:
            return _state(
                "stage_established",
                f"Stage established - {tnm['stage_group']}",
                f"T, N, M documented: {tnm['t']} {tnm['n']} {tnm['m']}.",
            )
        if _staging_activity(case, intake, active):
            return _state(
                "stage_in_progress",
                "Staging in progress",
                "Histology confirmed; staging evidence incomplete - stage not yet assignable.",
            )
        return _state(
            "histology_confirmed",
            "Histology confirmed - staging incomplete",
            "Tissue diagnosis exists; TNM staging evidence is still missing.",
        )
    if tissue in _PENDING_TISSUE:
        return _state(
            "tissue_pending",
            "Tissue sampling pending",
            "Biopsy indicated or in progress - histology must confirm malignancy.",
        )
    pathology_report = (case.get("metadata") or {}).get("pathology_report", "")
    if "pathology" in case.get("modalities", []) and pathology_report:
        if _MALIGNANCY.search(pathology_report) and not histology:
            return _state(
                "malignancy_confirmed",
                "Malignancy confirmed - histology detail pending",
                "Pathology report states malignancy; tumor type not yet recorded.",
            )
    if _has_imaging(case, intake):
        notes = case.get("clinical_notes", "")
        size_hits = [v for v in _values(active, "lesion_longest_mm")]
        big = any(float(v) >= 8 for v in size_hits if v.replace(".", "", 1).isdigit())
        if big or _SUSPICIOUS.search(notes):
            return _state(
                "malignancy_suspected",
                "Malignancy suspected (imaging only)",
                "Suspicious imaging features recorded - cancer cannot be confirmed "
                "without tissue or further evidence.",
            )
        return _state(
            "abnormal_finding",
            "Abnormal finding",
            "Imaging abnormality recorded but not yet suspicious for malignancy.",
        )
    return _state(
        "no_evidence",
        "Insufficient evidence",
        "No imaging or tissue evidence recorded - cannot diagnose cancer.",
    )
