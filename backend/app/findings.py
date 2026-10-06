"""Deterministic evidence extraction from documents (no LLM).

Every extracted value keeps its source document; the API writes them as
pending findings that a clinician can accept / edit / reject / mark unknown.
"""

import re

from app.imaging import extract_imaging_findings

_MM = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*mm\b", re.I)
_CM = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*cm\b", re.I)
_HISTOLOGY = re.compile(
    r"\b(adenocarcinoma|squamous cell carcinoma|small cell carcinoma|sclc|nsclc)\b",
    re.I,
)
_NODAL = re.compile(r"station\s*(\d{1,2}[a-z]?)\s+node\s+(positive|negative)", re.I)
_ADEQUACY = re.compile(r"non-?diagnostic|insufficient\s+(?:tissue|sample)", re.I)
_MET_NEG = re.compile(
    r"no\s+(?:evidence\s+of\s+)?(?:distant\s+)?metasta|without\s+distant\s+metasta",
    re.I,
)
_MET_ORGAN = re.compile(r"\b(brain|bone|adrenal|liver)\b[^.]*", re.I)
_MET_PLEURAL = re.compile(r"pleural effusion|pleural nodularity|pericardial", re.I)
_MET_WORD = re.compile(r"metasta\w*", re.I)
_PRIMARY_OTHER = re.compile(
    r"consistent with (?:a )?metasta|favor(?:s)? metasta|secondary (?:deposit|tumor)|"
    r"metastatic disease from",
    re.I,
)


def _size_value(text: str) -> str | None:
    mm = extract_imaging_findings(text).get("max_mm")
    if mm:
        return str(int(mm)) if float(mm) == int(mm) else str(mm)
    cms = [float(v) * 10 for v in _CM.findall(text)]
    if not cms:
        mms = [float(v) for v in _MM.findall(text)]
        if not mms:
            return None
        cms = mms
    best = max(cms)
    return str(int(best)) if best == int(best) else str(best)


def extract_findings(kind: str, text: str) -> list[dict]:
    """Extract evidence findings from document text. kind kept as provenance."""
    if not text or not text.strip():
        return []
    out: list[dict] = []

    def add(key: str, value: str, confidence: str = "high") -> None:
        out.append({"key": key, "value": value, "confidence": confidence})

    if kind in {"imaging_report", "ct", "notes"}:
        size = _size_value(text)
        if size:
            add("lesion_longest_mm", size)
    m = _HISTOLOGY.search(text)
    if m:
        add("histology", m.group(1).lower())
    m = _NODAL.search(text)
    if m:
        add("nodal_pathology", f"station {m.group(1).lower()} {m.group(2).lower()}")
    m = _ADEQUACY.search(text)
    if m:
        add("tissue_adequacy", "non-diagnostic")
    if _MET_NEG.search(text):
        add("distant_metastasis", "documented_negative")
    elif _MET_WORD.search(text):
        organ = _MET_ORGAN.search(text)
        if organ:
            add("distant_metastasis", organ.group(1).lower(), "medium")
        elif _MET_PLEURAL.search(text):
            add("distant_metastasis", "pleural/pericardial", "medium")
        else:
            add("distant_metastasis", "documented_positive", "medium")
    elif _MET_PLEURAL.search(text):
        add("distant_metastasis", "pleural/pericardial")
    if _PRIMARY_OTHER.search(text):
        add("primary_origin", "other_primary_suspected")
    return out
