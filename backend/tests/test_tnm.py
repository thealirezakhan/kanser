"""TNM staging from documented evidence only; indeterminate otherwise."""

from app.tnm import stage_case


def _case(intake_extra=None, metadata=None):
    intake = {"age": 65, "sex": "male"}
    intake.update(intake_extra or {})
    return {"modalities": ["ct", "pathology"], "metadata": metadata or {}, "intake": intake}


def _f(key, value, verification="accepted"):
    return {"key": key, "value": value, "verification": verification}


def test_size_to_t_rules():
    cases = [
        (8, "cT1a"), (15, "cT1b"), (25, "cT1c"), (34, "cT2a"),
        (45, "cT2b"), (60, "cT3"), (75, "cT4"),
    ]
    for mm, t in cases:
        r = stage_case(_case(), [_f("lesion_longest_mm", str(mm))])
        assert r["t"] == t, f"{mm}mm -> {t}, got {r['t']}"
        assert r["determinable"] is False  # N/M missing


def test_no_size_no_t():
    r = stage_case(_case(), [])
    assert r["t"] is None
    assert r["determinable"] is False
    assert r["stage_group"] == "Stage indeterminate - insufficient evidence"


def test_nodal_rules():
    assert stage_case(_case(), [_f("nodal_pathology", "station 7 positive")])["n"] == "cN2"
    assert stage_case(_case(), [_f("nodal_pathology", "station 10R positive")])["n"] == "cN1"
    assert stage_case(_case(), [_f("nodal_pathology", "station 7 negative")])["n"] == "cN0"
    assert stage_case(_case(), [])["n"] is None


def test_metastasis_rules():
    assert stage_case(_case(), [_f("distant_metastasis", "brain lesion")])["m"] == "cM1b"
    assert stage_case(_case(), [_f("distant_metastasis", "pleural effusion")])["m"] == "cM1a"
    assert stage_case(_case(), [_f("distant_metastasis", "documented_negative")])["m"] == "cM0"
    assert stage_case(_case(), [])["m"] is None


def test_rejected_findings_ignored():
    r = stage_case(
        _case(),
        [_f("lesion_longest_mm", "75", verification="rejected")],
    )
    assert r["t"] is None, "rejected measurement must not stage"


def test_unknown_n_never_assumed_negative():
    r = stage_case(_case(), [_f("lesion_longest_mm", "15")])
    assert r["n"] is None
    assert r["determinable"] is False
    assert "indeterminate" in r["stage_group"].lower()


def test_stage_groups():
    cases = [
        (["lesion_longest_mm", "15", "nodal_pathology", "station 7 negative",
          "distant_metastasis", "documented_negative"], "Stage IA2"),
        (["lesion_longest_mm", "25", "nodal_pathology", "station 7 negative",
          "distant_metastasis", "documented_negative"], "Stage IA3"),
        (["lesion_longest_mm", "34", "nodal_pathology", "station 7 negative",
          "distant_metastasis", "documented_negative"], "Stage IB"),
        (["lesion_longest_mm", "45", "nodal_pathology", "station 7 negative",
          "distant_metastasis", "documented_negative"], "Stage IIA"),
        (["lesion_longest_mm", "60", "nodal_pathology", "station 7 negative",
          "distant_metastasis", "documented_negative"], "Stage IIB"),
        (["lesion_longest_mm", "25", "nodal_pathology", "station 10R positive",
          "distant_metastasis", "documented_negative"], "Stage IIB"),
        (["lesion_longest_mm", "34", "nodal_pathology", "station 7 positive",
          "distant_metastasis", "documented_negative"], "Stage IIIA"),
        (["lesion_longest_mm", "60", "nodal_pathology", "station 10R positive",
          "distant_metastasis", "documented_negative"], "Stage IIIA"),
        (["lesion_longest_mm", "15", "nodal_pathology", "station 7 positive",
          "distant_metastasis", "documented_negative"], "Stage IIIA"),
        (["lesion_longest_mm", "15", "nodal_pathology", "station 7 positive",
          "distant_metastasis", "brain lesion"], "Stage IVA"),
        (["lesion_longest_mm", "60", "nodal_pathology", "station 7 positive",
          "distant_metastasis", "documented_negative"], "Stage IIIB"),
    ]
    for flat, expected in cases:
        findings = [_f(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
        r = stage_case(_case(), findings)
        assert r["stage_group"] == expected, f"{flat} -> {expected}, got {r['stage_group']}"
        assert r["determinable"] is True


def test_metadata_fallback_for_size():
    r = stage_case(
        _case(metadata={"imaging_findings": '{"max_mm": 34}'}),
        [_f("nodal_pathology", "station 7 negative"),
         _f("distant_metastasis", "documented_negative")],
    )
    assert r["t"] == "cT2a"


def test_size_based_t_carrying_warning():
    r = stage_case(_case(), [_f("lesion_longest_mm", "34")])
    assert any("size" in w.lower() for w in r["warnings"])
    assert r["staging_system"] == "IASLC 8th edition (size-based simplification)"
