"""GAP-002: abstention / insufficient-evidence states."""

from app.abstention import evaluate_abstention


def _case(**kw):
    base = {"modalities": ["ct", "notes"], "clinical_notes": "spiculated nodule"}
    base.update(kw)
    return base


def test_no_pathology_abstains_histologic_diagnosis():
    out = evaluate_abstention(
        case=_case(),
        evidence=[{"id": "e1", "text": "guideline"}],
        diagnosis="Adenocarcinoma, Stage IA",
    )
    assert out is not None
    assert out["state"] == "insufficient_evidence"
    assert "pathology" in out["reason"].lower()
    assert out["resolvable_by"]
    assert any("pathology" in r.lower() for r in out["resolvable_by"])


def test_no_evidence_abstains():
    out = evaluate_abstention(
        case=_case(modalities=["ct"]),
        evidence=[],
        diagnosis="Stage I lesion",
    )
    assert out is not None
    assert out["state"] == "insufficient_evidence"
    assert "evidence" in out["reason"].lower()


def test_histologic_claim_with_pathology_does_not_abstain():
    out = evaluate_abstention(
        case=_case(modalities=["ct", "notes", "pathology"]),
        evidence=[{"id": "e1", "text": "guideline"}],
        diagnosis="Adenocarcinoma",
    )
    assert out is None


def test_imaging_claim_with_ct_and_evidence_does_not_abstain():
    out = evaluate_abstention(
        case=_case(modalities=["ct"]),
        evidence=[{"id": "e1", "text": "guideline"}],
        diagnosis="Suspicious spiculated nodule, unconfirmed",
    )
    assert out is None


def test_abstention_carries_known_and_unknown():
    out = evaluate_abstention(
        case=_case(),
        evidence=[],
        diagnosis="Adenocarcinoma",
    )
    assert out is not None
    assert out["known"]
    assert out["unknown"]


def test_run_result_carries_abstain_field():
    import asyncio
    import json as _json

    from app.pii import get_pii_guard
    from app.swarm import run_case

    class _LLM:
        name = "t"

        def complete(self, prompt: str) -> str:
            if "Consensus" in prompt:
                return _json.dumps({"diagnosis": "Adenocarcinoma", "confidence": 0.9})
            if "Clinician view" in prompt:
                return _json.dumps({"text": "Technical: stage IIIA disease."})
            if "Self-critic" in prompt:
                return _json.dumps({"warnings": [], "guideline": {"aligned": True, "note": ""}})
            if "Critique" in prompt:
                return _json.dumps({"adjusted": {}})
            if prompt.startswith(("Clinician view", "Patient view")):
                return _json.dumps({"text": "ok"})
            return _json.dumps({"hypothesis": "nodule", "confidence": 0.6})

    from app.schemas import CaseInput

    case = CaseInput(
        patient_ref="t", modalities=["ct", "notes"], clinical_notes="spiculated nodule"
    )
    final = asyncio.run(run_case(case, llm=_LLM(), guard=get_pii_guard()))
    ab = final["consensus"]["abstain"]
    assert ab is not None
    assert ab["state"] == "insufficient_evidence"
    assert final["consensus"]["confidence"] == 0.0


def test_diagnosis_state_no_pathology_is_suspicion():
    from app.abstention import derive_diagnosis_state

    assert (
        derive_diagnosis_state(modalities={"ct", "notes"}, abstain=None) == "suspicion"
    )


def test_diagnosis_state_with_pathology_is_working_diagnosis():
    from app.abstention import derive_diagnosis_state

    assert (
        derive_diagnosis_state(modalities={"ct", "notes", "pathology"}, abstain=None)
        == "working_diagnosis"
    )


def test_diagnosis_state_abstain_overrides():
    from app.abstention import derive_diagnosis_state

    ab = {"state": "insufficient_evidence", "reason": "x"}
    assert (
        derive_diagnosis_state(modalities={"ct"}, abstain=ab) == "insufficient_evidence"
    )


def test_run_result_carries_diagnosis_state():
    import asyncio
    import json as _json

    from app.abstention import derive_diagnosis_state  # noqa: F401
    from app.pii import get_pii_guard
    from app.schemas import CaseInput
    from app.swarm import run_case

    class _LLM:
        name = "t"

        def complete(self, prompt: str) -> str:
            if "Consensus" in prompt:
                return _json.dumps({"diagnosis": "Adenocarcinoma", "confidence": 0.9})
            if "Self-critic" in prompt:
                return _json.dumps(
                    {"warnings": [], "guideline": {"aligned": True, "note": ""}}
                )
            if "Critique" in prompt:
                return _json.dumps({"adjusted": {}})
            if prompt.startswith(("Clinician view", "Patient view")):
                return _json.dumps({"text": "ok"})
            return _json.dumps({"hypothesis": "nodule", "confidence": 0.6})

    case = CaseInput(
        patient_ref="t", modalities=["ct", "notes"], clinical_notes="nodule"
    )
    final = asyncio.run(run_case(case, llm=_LLM(), guard=get_pii_guard()))
    assert final["consensus"]["diagnosis_state"] == "insufficient_evidence"
