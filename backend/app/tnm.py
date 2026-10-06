"""TNM staging from documented evidence only (IASLC 8th, simplified).

Never treats missing evidence as negative. Size-based T carries an explicit
warning; anything undetermined yields "Stage indeterminate - insufficient
evidence".
"""

import json
import re

_INDETERMINATE = "Stage indeterminate - insufficient evidence"
_SYSTEM = "IASLC 8th edition (size-based simplification)"
_T_RULES = [(10, "cT1a"), (20, "cT1b"), (30, "cT1c"), (40, "cT2a"), (50, "cT2b"), (70, "cT3")]
_STATION = re.compile(r"station\s*(\d{1,2})", re.I)

# {t: {n: stage}} for M0 combinations with high-confidence IASLC 8th mapping;
# anything not listed (incl. N3, which station-based extraction cannot reach) is indeterminate
_GROUPS: dict[str, dict[str, str]] = {
    "cT1a": {"cN0": "Stage IA1", "cN1": "Stage IIB", "cN2": "Stage IIIA"},
    "cT1b": {"cN0": "Stage IA2", "cN1": "Stage IIB", "cN2": "Stage IIIA"},
    "cT1c": {"cN0": "Stage IA3", "cN1": "Stage IIB", "cN2": "Stage IIIA"},
    "cT2a": {"cN0": "Stage IB", "cN1": "Stage IIB", "cN2": "Stage IIIA"},
    "cT2b": {"cN0": "Stage IIA", "cN1": "Stage IIB", "cN2": "Stage IIIA"},
    "cT3": {"cN0": "Stage IIB", "cN1": "Stage IIIA", "cN2": "Stage IIIB"},
    "cT4": {"cN2": "Stage IIIB"},
}


def _active(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("verification") != "rejected"]


def _last(findings: list[dict], key: str) -> dict | None:
    hits = [f for f in findings if f.get("key") == key]
    return hits[-1] if hits else None


def _t_size(case: dict, findings: list[dict]) -> tuple[str | None, str]:
    f = _last(findings, "lesion_longest_mm")
    if f:
        try:
            mm = float(f["value"])
        except ValueError:
            mm = 0.0
        if mm > 0:
            for cap, t in _T_RULES:
                if mm <= cap:
                    doc = f.get("source_doc", "documented")
                    return t, f"lesion_longest_mm={f['value']} ({doc})"
            return "cT4", f"lesion_longest_mm={f['value']}"
    try:
        data = json.loads((case.get("metadata") or {}).get("imaging_findings") or "{}")
        mm = float(data.get("max_mm") or 0)
    except (ValueError, TypeError, json.JSONDecodeError):
        mm = 0.0
    if mm > 0:
        for cap, t in _T_RULES:
            if mm <= cap:
                return t, f"imaging_findings.max_mm={mm}"
        return "cT4", f"imaging_findings.max_mm={mm}"
    return None, ""


def _n(findings: list[dict]) -> tuple[str | None, str]:
    f = _last(findings, "nodal_pathology")
    if not f:
        return None, ""
    value = f["value"].lower()
    doc = f.get("source_doc", "documented")
    if "negative" in value:
        return "cN0", f"nodal_pathology={value} ({doc})"
    m = _STATION.search(value)
    if m and "positive" in value:
        station = int(m.group(1))
        if station >= 10:
            return "cN1", f"nodal_pathology={value} ({doc})"
        if station <= 9:
            return "cN2", f"nodal_pathology={value} ({doc})"
    return None, ""


def _m(findings: list[dict]) -> tuple[str | None, str]:
    f = _last(findings, "distant_metastasis")
    if not f:
        return None, ""
    value = f["value"].lower()
    doc = f.get("source_doc", "documented")
    if value == "documented_negative":
        return "cM0", f"distant_metastasis={value} ({doc})"
    if "pleural" in value or "pericardial" in value:
        return "cM1a", f"distant_metastasis={value} ({doc})"
    return "cM1b", f"distant_metastasis={value} ({doc})"


def _stage_group(t: str | None, n: str | None, m: str | None) -> str | None:
    if not (t and n and m):
        return None
    if m == "cM1c":
        return "Stage IVB"
    if m in {"cM1a", "cM1b"}:
        return "Stage IVA"
    if m != "cM0":
        return None
    return _GROUPS.get(t, {}).get(n)


def stage_case(case: dict, findings: list[dict]) -> dict:
    """Stage a case strictly from documented, non-rejected evidence."""
    active = _active(findings)
    t, t_ev = _t_size(case, active)
    n, n_ev = _n(active)
    m, m_ev = _m(active)
    group = _stage_group(t, n, m)
    warnings: list[str] = []
    if t:
        warnings.append(
            "T stage is a size-based simplification; invasion, atelectasis and "
            "other T features are not assessed from this evidence"
        )
    return {
        "staging_system": _SYSTEM,
        "t": t,
        "n": n,
        "m": m,
        "stage_group": group or _INDETERMINATE,
        "determinable": bool(group),
        "evidence": {"t": t_ev, "n": n_ev, "m": m_ev},
        "warnings": warnings,
    }
