"""Claim-level output validation (GAP-001).

Literature must come from retrieved evidence; clinical claims are gated on the
structured data that could support them. Anything blocked is replaced with an
explicit UNSUPPORTED CLAIM marker, never silently shown as fact.
"""

import re

UNSUPPORTED = "[UNSUPPORTED CLAIM: removed - no supporting case data]"

_MOLECULAR_RE = re.compile(
    r"\b(EGFR|KRAS|ALK|ROS1|BRAF|HER2|MET|RET|NTRK|TP53)\b"
    r"|\bPD-L1\b|\bVAF\b|\bTPS\b|\bmolecular profil\w*",
    re.IGNORECASE,
)
_BBOX_RE = re.compile(r"bounding box|slice \d+|coordinates \(", re.IGNORECASE)

_VISION_MODALITIES = {"ct", "cxr"}


def sanitize_literature(literature: list[str], allowed_ids: set[str]) -> list[str]:
    """Keep only citations whose id appears in the retrieved evidence set."""
    kept = [str(x) for x in literature if str(x) in allowed_ids]
    if kept:
        return kept
    # LLM gave nothing usable - fall back to actual retrieved ids
    return [i for i in sorted(allowed_ids)][:8]


def gate_clinician_text(
    text: str,
    modalities: set[str] | list[str],
    vision_ran: bool = False,
) -> str:
    """Strip molecular/bounding-box claims the case data cannot support."""
    mods = set(modalities)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for s in sentences:
        if _MOLECULAR_RE.search(s) and "genomics" not in mods:
            kept.append(UNSUPPORTED)
            continue
        if _BBOX_RE.search(s) and not vision_ran:
            kept.append(UNSUPPORTED)
            continue
        kept.append(s)
    return " ".join(kept)
