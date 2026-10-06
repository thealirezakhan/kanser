"""Contradiction detection across evidence findings.

Conflicts are reported, never silently resolved: the clinician accepts,
edits, or rejects findings; until then the case state is 'uncertain'.
"""

_SIZE_TOLERANCE_MM = 2.0


def _active(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("verification") != "rejected"]


def _values(findings: list[dict], key: str) -> list[str]:
    return [str(f.get("value", "")).strip() for f in findings if f.get("key") == key]


def _conflict(kind: str, key: str, findings: list[dict]) -> dict:
    return {
        "type": kind,
        "key": key,
        "values": [
            {
                "value": str(f.get("value", "")),
                "source_doc": f.get("source_doc", ""),
                "verification": f.get("verification", "pending"),
            }
            for f in findings
            if f.get("key") == key
        ],
    }


def detect_conflicts(findings: list[dict]) -> list[dict]:
    active = _active(findings)
    conflicts: list[dict] = []

    sizes = [f for f in active if f.get("key") == "lesion_longest_mm"]
    parsed = []
    for f in sizes:
        try:
            parsed.append(float(str(f["value"])))
        except ValueError:
            continue
    if len(parsed) > 1 and max(parsed) - min(parsed) > _SIZE_TOLERANCE_MM:
        conflicts.append(_conflict("measurement_conflict", "lesion_longest_mm", sizes))

    hists = [f for f in active if f.get("key") == "histology"]
    distinct = {v.lower() for v in _values(hists, "histology")}
    if len(distinct) > 1:
        conflicts.append(_conflict("histology_conflict", "histology", hists))

    conflicts.sort(key=lambda c: c["key"])
    return conflicts
