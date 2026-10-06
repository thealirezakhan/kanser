"""Data Standardization Agent: cleans and maps heterogeneous intake into one schema."""

import csv
import io
import re

SCHEMA_VERSION = "1.0"

_KV_LINE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9 /%_.-]{0,60})\s*[:=]\s*"
    r"([-+0-9.]+)\s*([A-Za-z/%]*\s*[A-Za-z]*)\s*$"
)
_SNV = re.compile(r"^(rs\d+|[A-Z][A-Z0-9]{1,9})$")
_PATHOLOGY = re.compile(
    r"\bbiopsy\b|\bspecimen\b|adenocarcinoma|squamous cell|histolog|cytolog|"
    r"immunohistochemistry|\bIHC\b|lymphovascular",
    re.I,
)
_IMAGING_RPT = re.compile(
    r"CT chest|computed tomography|pet/?ct|pulmonary nodule|nodule measures|"
    r"\b(?:RUL|LUL|RLL|LLL)\b|\b\d{1,2}(?:\.\d+)?\s*mm\b",
    re.I,
)


def _flag(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


def classify_file(filename: str, text: str) -> str | None:
    name = filename.lower()
    if name.endswith(".vcf"):
        return "genomics"
    if name.endswith((".jpg", ".jpeg", ".png", ".dcm", ".dicom")):
        return "ct"
    if name.endswith(".csv"):
        head = text[:200].lower()
        if "value" in head or "test" in head or "analyte" in head or "hemoglobin" in head:
            return "labs"
        return None
    if name.endswith((".txt", ".md", ".pdf")):
        if _PATHOLOGY.search(text):
            return "pathology"
        if _IMAGING_RPT.search(text):
            return "imaging_report"
        return "notes"
    return None


def parse_labs(text: str) -> tuple[dict[str, str], list[dict]]:
    """Parse lab values from key:value lines or name,value,unit CSV."""
    values: dict[str, str] = {}
    flags: list[dict] = []
    stripped = text.strip()
    if not stripped:
        return {}, [_flag("warn", "labs_empty", "lab payload is empty")]

    if "," in stripped.splitlines()[0]:
        try:
            rows = list(csv.DictReader(io.StringIO(stripped)))
        except csv.Error:
            rows = []
        for row in rows:
            keys = {k.lower().strip(): v for k, v in row.items() if k}
            name = keys.get("name") or keys.get("test") or keys.get("analyte") or ""
            value = keys.get("value", "")
            unit = keys.get("unit", "")
            if name and value:
                values[name.strip().lower()] = f"{value.strip()} {unit}".strip()
        if values:
            return values, flags
        flags.append(_flag("warn", "labs_unparsed", "CSV header did not match lab schema"))

    for line in stripped.splitlines():
        m = _KV_LINE.match(line)
        if m:
            name, value, unit = m.group(1), m.group(2), m.group(3)
            values[name.strip().lower()] = f"{value} {unit}".strip()
    if not values and not flags:
        flags.append(_flag("warn", "labs_unparsed", "no lab values found in payload"))
    return values, flags


def parse_vcf(text: str) -> tuple[list[dict], list[dict]]:
    """Parse simple VCF: gene from ID column or INFO GENE= field."""
    variants: list[dict] = []
    flags: list[dict] = []
    lines = text.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("#CHROM")), None
    )
    if header_idx is None:
        return [], [_flag("error", "vcf_malformed", "missing #CHROM header line")]

    for line in lines[header_idx + 1 :]:
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 5:
            continue
        chrom, pos, vid, ref, alt = cols[0], cols[1], cols[2], cols[3], cols[4]
        info = cols[7] if len(cols) > 7 else ""
        gene = ""
        info_gene = re.search(r"(?:^|;)GENE=([A-Za-z0-9-]+)", info)
        if info_gene:
            gene = info_gene.group(1).upper()
        elif _SNV.match(vid) and not vid.startswith("rs"):
            gene = vid.upper()
        elif _SNV.match(vid):
            gene = vid
        variants.append(
            {"gene": gene or "unknown", "chrom": chrom, "pos": pos, "ref": ref, "alt": alt}
        )
    if not variants:
        flags.append(_flag("warn", "vcf_empty", "VCF contains no variant rows"))
    return variants, flags


def standardize_case(case: dict) -> dict:
    """Map a case record into the unified intake schema with quality flags."""
    modalities = set(case.get("modalities", []))
    notes = case.get("clinical_notes", "")
    metadata = case.get("metadata", {})
    flags: list[dict] = []

    labs: dict = {"values": {}}
    if "labs" in modalities or "labs_raw" in metadata:
        values, lab_flags = parse_labs(metadata.get("labs_raw", ""))
        labs["values"] = values
        flags.extend(lab_flags)

    genomics: dict = {"variants": []}
    if "genomics" in modalities or "vcf" in metadata:
        variants, vcf_flags = parse_vcf(metadata.get("vcf", ""))
        genomics["variants"] = variants
        flags.extend(vcf_flags)

    if "notes" in modalities and not notes.strip():
        flags.append(_flag("warn", "notes_empty", "notes modality declared but empty"))

    imaging = []
    if metadata.get("imaging_findings"):
        imaging.append(
            {"modality": "ct", "findings": str(metadata["imaging_findings"])[:4000]}
        )

    for mod in modalities - {"ct", "cxr", "pathology", "genomics", "labs", "notes"}:
        flags.append(_flag("warn", "unknown_modality", f"unsupported modality: {mod}"))

    return {
        "schema_version": SCHEMA_VERSION,
        "patient_ref": case.get("patient_ref", ""),
        "modalities": sorted(modalities),
        "notes": notes,
        "imaging": imaging,
        "labs": labs,
        "genomics": genomics,
        "quality_flags": flags,
    }
