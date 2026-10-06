"""GAP-001: claim-level output validation — literature whitelist + claim gating."""

from app.claims import gate_clinician_text, sanitize_literature


def test_literature_whitelisted_against_retrieved_evidence():
    out = sanitize_literature(
        ["guideline-2024", "Smith et al., 2023", "Johnson & Lee, 2022"],
        allowed_ids={"guideline-2024", "evidence-7"},
    )
    assert out == ["guideline-2024"]


def test_literature_empty_allowed_ids_means_no_citations():
    assert sanitize_literature(["Smith et al., 2023"], allowed_ids=set()) == []


def test_literature_falls_back_to_retrieved_when_llm_gives_none():
    out = sanitize_literature([], allowed_ids={"evidence-1"})
    assert out == ["evidence-1"]


def test_molecular_claim_blocked_without_genomics_data():
    text = (
        "Molecular profiling: EGFR L858R (VAF 12%), PD-L1 TPS 30%. "
        "The nodule is spiculated."
    )
    gated = gate_clinician_text(text, modalities={"ct", "notes"})
    assert "EGFR" not in gated
    assert "PD-L1" not in gated
    assert "UNSUPPORTED CLAIM" in gated
    assert "spiculated" in gated  # radiology claim allowed with ct


def test_molecular_claim_allowed_with_genomics_modality():
    text = "EGFR L858R detected, VAF 12%."
    gated = gate_clinician_text(text, modalities={"ct", "genomics"})
    assert "EGFR L858R" in gated


def test_bounding_box_claim_blocked_without_vision_run():
    text = "Suspicious opacity, bounding box coordinates (120, 80) on CT slice 45."
    gated = gate_clinician_text(text, modalities={"ct"}, vision_ran=False)
    assert "bounding box" not in gated.lower()
    assert "UNSUPPORTED CLAIM" in gated
    gated2 = gate_clinician_text(text, modalities={"ct"}, vision_ran=True)
    assert "bounding box" in gated2.lower()
