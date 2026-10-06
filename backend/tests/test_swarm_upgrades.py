import asyncio
import json

from test_swarm import FakeLLM, _case

from app.pii import get_pii_guard
from app.swarm import run_case


class _RagStub:
    def __init__(self, hits):
        self.hits = hits

    def __call__(self, query: str) -> list[dict]:
        return list(self.hits)


def _hits():
    return [
        {
            "id": "pmid-1",
            "text": "spiculated nodule malignancy rate",
            "metadata": {"year": 2024},
            "score": 0.9,
        },
        {
            "id": "pmid-2",
            "text": "unrelated cardiology study",
            "metadata": {"year": 2025},
            "score": 0.8,
        },
    ]


def test_agents_report_missing_flags():
    llm = FakeLLM()
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert final["reports"]["radiology"]["missing_flags"] == ["dicom_scan"]
    assert final["reports"]["clinical"]["missing_flags"] == ["labs_panel"]


def test_consensus_carries_confidence_calibration():
    # non-abstaining case: evidence present, imaging-level (non-histologic) dx
    class _ImagingLLM(FakeLLM):
        def complete(self, prompt: str) -> str:
            if "Consensus" in prompt:
                return json.dumps(
                    {"diagnosis": "Suspicious spiculated nodule, unconfirmed", "confidence": 0.8}
                )
            return super().complete(prompt)

    llm = _ImagingLLM()
    final = asyncio.run(
        run_case(_case(), llm=llm, guard=get_pii_guard(), rag=_RagStub(_hits()))
    )
    cal = final["consensus"]["calibration"]
    assert set(cal["per_agent"]) == {"radiology", "clinical"}
    assert 0.0 < cal["overall"] <= 1.0
    assert "labs_panel" in cal["reason"]
    assert "dicom_scan" in cal["reason"]
    assert final["consensus"]["abstain"] is None
    assert final["consensus"]["confidence"] == cal["overall"]


def test_staged_fusion_events_emitted():
    llm = FakeLLM()
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    nodes = {
        e["node"]
        for e in final["events"]
        if e.get("type") == "agent_step" and "fusion" in str(e.get("node", ""))
    }
    assert {"fusion_image", "fusion_clinical", "fusion_knowledge"} <= nodes


def test_plan_event_emitted_with_agents_and_tools():
    llm = FakeLLM()
    events: list[dict] = []
    asyncio.run(
        run_case(_case(), llm=llm, guard=get_pii_guard(), on_event=events.append)
    )
    plan = next(e for e in events if e["type"] == "plan")
    assert "radiology" in plan["agents"]
    assert "genomics" not in plan["agents"]
    assert "rag" in plan["tools"]
    assert plan["reasons"]


def test_plan_overrides_routing_activated():
    llm = FakeLLM()
    final = asyncio.run(run_case(_case(), llm=llm, guard=get_pii_guard()))
    assert final["plan"]["agents"] == final["routing"]["activated"]
    assert "pathology" in final["routing"]["dropped"]


def test_evidence_relevance_drop():
    class DropLLM(FakeLLM):
        def complete(self, prompt: str) -> str:
            if "Relevance check" in prompt:
                return json.dumps({"drop": ["pmid-2"]})
            return super().complete(prompt)

    llm = DropLLM()
    final = asyncio.run(
        run_case(
            _case(),
            llm=llm,
            guard=get_pii_guard(),
            rag=_RagStub(_hits()),
        )
    )
    kept_ids = {h["id"] for h in final["evidence"]}
    assert kept_ids == {"pmid-1"}


def test_evidence_irrelevant_not_dropped_by_default():
    llm = FakeLLM()
    final = asyncio.run(
        run_case(_case(), llm=llm, guard=get_pii_guard(), rag=_RagStub(_hits()))
    )
    assert {h["id"] for h in final["evidence"]} == {"pmid-1", "pmid-2"}


def test_guideline_discrepancy_becomes_warning():
    class GuidelineLLM(FakeLLM):
        def complete(self, prompt: str) -> str:
            if "Self-critic" in prompt:
                return json.dumps(
                    {
                        "warnings": ["mimics considered"],
                        "guideline": {
                            "aligned": False,
                            "note": "NCCN requires tissue confirmation before staging",
                        },
                    }
                )
            return super().complete(prompt)

    final = asyncio.run(
        run_case(_case(), llm=GuidelineLLM(), guard=get_pii_guard())
    )
    assert final["guideline"]["aligned"] is False
    assert any("NCCN" in w for w in final["warnings"])


def test_explain_carries_alternatives_reasons():
    class RichLLM(FakeLLM):
        def complete(self, prompt: str) -> str:
            if "Clinician view" in prompt:
                return json.dumps(
                    {
                        "text": "Technical breakdown",
                        "alternatives": ["granuloma", "hamartoma"],
                        "reasons": ["spiculation", "142d doubling time"],
                        "literature": ["PMID 3829104"],
                    }
                )
            return super().complete(prompt)

    final = asyncio.run(run_case(_case(), llm=RichLLM(), guard=get_pii_guard()))
    assert final["explain"]["alternatives"] == ["granuloma", "hamartoma"]
    assert "spiculation" in final["explain"]["reasons"]
    # GAP-001: LLM-supplied citations must match retrieved evidence; with no
    # rag stub there is no evidence, so fabricated "PMID 3829104" is dropped
    assert final["explain"]["literature"] == []


def test_explain_literature_defaults_from_evidence():
    llm = FakeLLM()
    final = asyncio.run(
        run_case(_case(), llm=llm, guard=get_pii_guard(), rag=_RagStub(_hits()))
    )
    assert "pmid-1" in final["explain"]["literature"][0]
