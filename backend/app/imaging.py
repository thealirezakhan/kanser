"""Imaging file extraction: DICOM headers and radiology report measurements."""

import re
from pathlib import Path

_SIZE = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:[x×]\s*\d{1,2}(?:\.\d+)?\s*)?mm\b", re.I)
_LOBE = re.compile(
    r"\b(RUL|LUL|RLL|LLL|RML|right upper lobe|left upper lobe|right lower lobe|"
    r"left lower lobe|middle lobe|lingula)\b",
    re.I,
)
_CT_TEXT = re.compile(r"\bCT\b|computed tomography|pet/?ct|tomographic", re.I)
_CXR_TEXT = re.compile(r"x-?ray|cxr", re.I)


def extract_dicom_header(path: Path) -> dict | None:
    """Pull header tags from a DICOM file without decoding pixel data."""
    try:
        import pydicom

        ds = pydicom.dcmread(str(path), stop_before_pixels=True)
    except Exception:
        return None
    out: dict[str, str] = {}
    for tag, key in (
        ("Modality", "modality"),
        ("BodyPartExamined", "body_part"),
        ("StudyDate", "study_date"),
        ("StudyDescription", "study_description"),
        ("SeriesDescription", "series_description"),
        ("Manufacturer", "manufacturer"),
    ):
        value = str(getattr(ds, tag, "") or "").strip()
        if value:
            out[key] = value
    return out or None


def extract_imaging_findings(text: str) -> dict:
    """Pull measurable findings (sizes in mm, lobes) from radiology report text."""
    sizes = [float(m) for m in _SIZE.findall(text)]
    lobes: list[str] = []
    for m in _LOBE.findall(text):
        label = m.upper() if len(m) <= 3 else m.title()
        if label not in lobes:
            lobes.append(label)
    return {"max_mm": max(sizes) if sizes else None, "lobes": lobes}


def classify_imaging_modality(text: str) -> str:
    """Report text without CT markers is treated as a chest x-ray."""
    return "ct" if _CT_TEXT.search(text) else ("cxr" if _CXR_TEXT.search(text) else "ct")
