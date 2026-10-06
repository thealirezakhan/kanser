"""Abstention / insufficient-evidence states (GAP-002).

Deterministic gate: blocks diagnosis-class output the case data cannot support
and returns an explicit abstention record instead of a confident number.
"""

import re

# tissue-diagnosis language that only pathology can ground
_HISTOLOGIC_RE = re.compile(
    r"\b(adenocarcinoma|carcinoma|squamous|nsclc|sclc|large cell|malignant cells|"
    r"positive for (cancer|malignancy))\b",
    re.IGNORECASE,
)

_HISTOLOGIC_RESOLVABLE = [
    "pathology report (biopsy or cytology)",
    "molecular testing on tissue specimen",
]

_EVIDENCE_RESOLVABLE = [
    "retrieve supporting clinical evidence",
    "upload missing imaging or reports",
]

DIAGNOSIS_STATES = (
    "insufficient_evidence",
    "finding",
    "suspicion",
    "working_diagnosis",
    "confirmed",
    "staged",
    "treatment_context",
)


def derive_diagnosis_state(
    modalities: set[str] | list[str],
    abstain: dict | None,
) -> str:
    """State taxonomy for the report (GAP-015). Abstention always wins."""
    if abstain:
        return "insufficient_evidence"
    if "pathology" not in set(modalities):
        return "suspicion"
    return "working_diagnosis"


def evaluate_abstention(
    case: dict,
    evidence: list,
    diagnosis: str,
) -> dict | None:
    """Return abstention record when diagnosis-class output lacks support.

    None = case has enough to render a qualified (non-abstaining) statement.
    """
    mods = set(case.get("modalities", []))
    notes = case.get("clinical_notes", "") or ""

    known: list[str] = []
    if "ct" in mods or "cxr" in mods:
        known.append("imaging modality available")
    if notes:
        known.append("clinical notes available")
    if evidence:
        known.append(f"{len(evidence)} supporting evidence hit(s)")

    if evidence:
        unknown: list[str] = []
        if "pathology" not in mods and _HISTOLOGIC_RE.search(diagnosis):
            unknown.append("histologic diagnosis (no pathology specimen)")
        if not unknown:
            return None
        resolvable = _HISTOLOGIC_RESOLVABLE
        reason = (
            "cannot establish histologic diagnosis - pathology unavailable"
        )
    else:
        unknown = ["no qualifying supporting evidence retrieved"]
        resolvable = _EVIDENCE_RESOLVABLE
        reason = "no qualifying evidence for a diagnosis-class statement"

    return {
        "state": "insufficient_evidence",
        "reason": reason,
        "known": known or ["case record present"],
        "unknown": unknown,
        "resolvable_by": resolvable,
    }
