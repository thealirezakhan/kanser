import asyncio
import json

from app.llm import LocalLLM
from app.pii import get_pii_guard
from app.schemas import CaseInput
from app.swarm import run_case


class FakeLLM:
    """Prompt-driven fake: returns agent-specific JSON, records everything."""

    def __init__(self, resolve_debate=False, warnings=None):
        self.prompts: list[str] = []
        self.resolve_debate = resolve_debate
        self.warnings = warnings or []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if "Self-critic" in prompt:
            return json.dumps({"warnings": self.warnings})
        if "Critique" in prompt:
            if self.resolve_debate:
                return json.dumps(
                    {"adjusted": {"radiology": 0.7, "clinical": 0.7}}
                )
            return json.dumps({"adjusted": {}})
        if "role: radiology" in prompt:
            return json.dumps({"hypothesis": "2cm spiculated nodule", "confidence": 0.9})
        if "role: clinical" in prompt:
            return json.dumps({"hypothesis": "cough, no fever", "confidence": 0.5})
        if "role: pathology" in prompt:
            return json.dumps({"hypothesis": "atypical cells", "confidence": 0.75})
        if "Consensus" in prompt:
            return json.dumps({"diagnosis": "Stage I adenocarcinoma", "confidence": 0.8})
        if "Clinician view" in prompt:
            return json.dumps({"text": "Technical: nodule 2cm, EGFR wildtype."})
        if "Patient view" in prompt:
            return json.dumps({"text": "A small spot was found. Next step: biopsy."})
        return json.dumps({"hypothesis": "unknown", "confidence": 0.5})


def _case(notes="small nodule", modalities=None):
    return CaseInput(
        patient_ref="t",
        modalities=modalities or ["ct", "notes"],
        clinical_notes=notes,
    )


def test_full_run_completes_with_mock_llm():
    llm = FakeLLM()
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert final["consensus"]["diagnosis"] == "Stage I adenocarcinoma"
    assert "radiology" in final["reports"]
    assert final["explain"]["patient"]
    assert final["status"] == "completed"


def test_missing_genomics_never_calls_genomics_agent():
    llm = FakeLLM()
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert not any("role: genomics" in p for p in llm.prompts)
    assert "genomics" in final["routing"]["dropped"]


def test_conflict_triggers_debate_loop():
    llm = FakeLLM(resolve_debate=False)
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert final["debate_rounds"] >= 1


def test_debate_bounded_at_three_then_consensus():
    llm = FakeLLM(resolve_debate=False)
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert final["debate_rounds"] <= 3
    assert final["consensus"]["diagnosis"]


def test_debate_resolves_when_agents_agree():
    llm = FakeLLM(resolve_debate=True)
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert final["debate_rounds"] == 1


def test_events_carry_agent_steps():
    llm = FakeLLM()
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    kinds = {e.get("type") for e in final["events"]}
    assert "agent_step" in kinds
    nodes = {e.get("node") for e in final["events"] if e.get("type") == "agent_step"}
    assert "radiology" in nodes
    assert "genomics" not in nodes


def test_all_llm_prompts_scrubbed_of_phi():
    llm = FakeLLM()
    dirty = _case(notes="Patient John Smith, MRN 12345678, spiculated nodule")
    final = asyncio.run(run_case(dirty, llm=llm, guard=get_pii_guard()))
    for p in llm.prompts:
        assert "John Smith" not in p
        assert "12345678" not in p
    assert final["status"] == "completed"


def test_self_critic_warnings_surface():
    llm = FakeLLM(resolve_debate=True, warnings=["granuloma can mimic this CT pattern"])
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert any("granuloma" in w for w in final["warnings"])


def test_diagnose_endpoint_queues_run():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    cid = client.post(
        "/api/cases", json={"patient_ref": "d", "modalities": ["ct"]}
    ).json()["data"]["id"]
    r = client.post(f"/api/cases/{cid}/diagnose")
    assert r.status_code == 202
    run_id = r.json()["data"]["run_id"]
    rr = client.get(f"/api/runs/{run_id}")
    assert rr.status_code == 200
    assert rr.json()["data"]["status"] in {"queued", "running", "completed"}


def test_local_llm_no_network():
    out = LocalLLM().complete("role: radiology analyze")
    data = json.loads(out)
    assert "hypothesis" in data
    assert 0 <= data["confidence"] <= 1


def test_agent_step_events_carry_detail():
    llm = FakeLLM(warnings=["granuloma considered"])
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    done = {}
    for e in final["events"]:
        if e.get("type") == "agent_step" and "detail" in e:
            done.setdefault(e["node"], e)
    assert done["radiology"]["detail"] == "2cm spiculated nodule"
    assert "Stage I adenocarcinoma" in done["consensus"]["detail"]
    assert "granuloma" in done["self_critic"]["detail"]
    assert "Technical:" in done["explain"]["detail"]
    assert "adjusted" in done["debate"]["detail"]


def test_explain_prompts_declare_json():
    llm = FakeLLM()
    asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    views = [p for p in llm.prompts if "Clinician view" in p or "Patient view" in p]
    assert views, "no explain prompts captured"
    assert all("json" in p.lower() for p in views)
