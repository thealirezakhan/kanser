import json
from dataclasses import asdict
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.system1 import RoutingMap, route_case


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


def _concat(a: list, b: list) -> list:
    return list(a) + list(b)


class CaseState(TypedDict):
    case: dict
    routing: dict
    reports: Annotated[dict, _merge]
    events: Annotated[list, _concat]
    # plain list: evidence_verify REPLACES rag_evidence output, no concat
    evidence: list
    warnings: Annotated[list, _concat]
    debate_rounds: int
    critic_rounds: int
    consensus: dict
    explain: dict
    status: str


AGENT_NODES = ("radiology", "pathology", "genomics", "clinical")


class GuardedLLM:
    """Zero-trust egress: scrub every prompt before it reaches an LLM."""

    def __init__(self, llm, guard) -> None:
        self._llm = llm
        self._guard = guard

    def complete(self, prompt: str) -> str:
        clean = self._guard.anonymize(prompt)
        self._guard.assert_clean(clean)
        return self._llm.complete(clean)


def _parse(raw: str, default: dict) -> dict:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else default
    except (json.JSONDecodeError, TypeError):
        return default


def _conflict(state: CaseState) -> bool:
    confs = [r["confidence"] for r in state["reports"].values()]
    return len(confs) > 1 and (max(confs) - min(confs)) >= 0.3


def build_graph(llm, rag=None):
    from app.rag import build_query, filter_evidence

    def fan_out(state: CaseState) -> list[str]:
        activated = [a for a in state["routing"]["activated"] if a in AGENT_NODES]
        return activated or ["rag_evidence"]

    def make_agent_node(name: str):
        async def node(state: CaseState) -> dict:
            prompt = (
                f"role: {name}\n"
                "Analyze this lung cancer case. Return JSON "
                '{"hypothesis": str, "confidence": float}.\n'
                f"Modalities available: {state['case']['modalities']}\n"
                f"Clinical notes: {state['case'].get('clinical_notes', '')}"
            )
            data = _parse(
                llm.complete(prompt),
                {"hypothesis": "unparsed output", "confidence": 0.5},
            )
            report = {
                "agent": name,
                "hypothesis": str(data.get("hypothesis", ""))[:2000],
                "confidence": float(data.get("confidence", 0.5)),
                "missing_flags": [],
            }
            return {
                "reports": {name: report},
                "events": [
                    {"type": "agent_step", "node": name, "status": "started"},
                    {
                        "type": "agent_step",
                        "node": name,
                        "status": "completed",
                        "confidence": report["confidence"],
                        "detail": report["hypothesis"],
                    },
                ],
            }

        return node

    async def rag_evidence(state: CaseState) -> dict:
        if rag is None:
            return {
                "evidence": [],
                "events": [
                    {
                        "type": "agent_step",
                        "node": "rag_evidence",
                        "status": "pending",
                        "reason": "no store configured",
                    }
                ],
            }
        try:
            hits = rag(build_query(state["reports"]))
            return {
                "evidence": hits,
                "events": [
                    {
                        "type": "agent_step",
                        "node": "rag_evidence",
                        "status": "completed",
                        "hits": len(hits),
                    }
                ],
            }
        except Exception:
            return {
                "evidence": [],
                "events": [
                    {"type": "evidence_unavailable", "reason": "store error"}
                ],
            }

    async def evidence_verify(state: CaseState) -> dict:
        kept, dropped = filter_evidence(
            state["evidence"], state["case"].get("metadata", {})
        )
        events = [
            {
                "type": "evidence",
                "citations": [
                    {
                        "id": h["id"],
                        "year": h.get("metadata", {}).get("year"),
                        "score": round(float(h.get("score", 0.0)), 3),
                    }
                    for h in kept
                ],
            },
            {
                "type": "agent_step",
                "node": "evidence_verify",
                "status": "completed",
                "kept": len(kept),
                "dropped": len(dropped),
            },
        ]
        return {"evidence": kept, "events": events}

    async def debate(state: CaseState) -> dict:
        prompt = (
            "Critique these conflicting agent reports and reweight confidence. "
            'Return JSON {"adjusted": {"agent_name": confidence}}.\n'
            + json.dumps({k: v["confidence"] for k, v in state["reports"].items()})
        )
        data = _parse(llm.complete(prompt), {"adjusted": {}})
        reports = dict(state["reports"])
        for agent, conf in data.get("adjusted", {}).items():
            if agent in reports:
                reports[agent]["confidence"] = float(conf)
        rounds = state["debate_rounds"] + 1
        return {
            "reports": reports,
            "debate_rounds": rounds,
                "events": [
                    {
                        "type": "agent_step",
                        "node": "debate",
                        "round": rounds,
                        "detail": f"adjusted={json.dumps(data.get('adjusted', {}))}",
                    },
                ],
        }

    async def consensus(state: CaseState) -> dict:
        prompt = (
            "Consensus: resolve via confidence-weighted reasoning, not majority vote. "
            'Return JSON {"diagnosis": str, "confidence": float}.\n'
            + json.dumps(
                {
                    "reports": {
                        k: v["hypothesis"] for k, v in state["reports"].items()
                    },
                    "evidence": state["evidence"],
                }
            )
        )
        data = _parse(
            llm.complete(prompt), {"diagnosis": "unresolved", "confidence": 0.0}
        )
        return {
            "consensus": data,
            "events": [
                {
                    "type": "agent_step",
                    "node": "consensus",
                    "status": "completed",
                    "detail": (
                        f"{data.get('diagnosis', '')} "
                        f"({float(data.get('confidence', 0)):.2f})"
                    ),
                }
            ],
        }

    async def self_critic(state: CaseState) -> dict:
        prompt = (
            "Self-critic: what alternative conditions (granuloma, pneumonia, ...) could "
            "mimic these findings? Check guideline alignment. "
            'Return JSON {"warnings": [str]}.\n'
            + json.dumps(
                {
                    "diagnosis": state["consensus"].get("diagnosis", ""),
                    "reports": {
                        k: v["hypothesis"] for k, v in state["reports"].items()
                    },
                }
            )
        )
        data = _parse(llm.complete(prompt), {"warnings": []})
        warnings = [str(w) for w in data.get("warnings", [])]
        return {
            "warnings": warnings,
            "critic_rounds": state["critic_rounds"] + 1,
            "events": [
                {
                    "type": "agent_step",
                    "node": "self_critic",
                    "status": "completed",
                    "detail": (
                        "; ".join(warnings) if warnings else "no alternatives flagged"
                    ),
                }
            ],
        }

    async def explain(state: CaseState) -> dict:
        notes = state["case"].get("clinical_notes", "")
        clinician = _parse(
            llm.complete(
                "Clinician view: technical breakdown with gene mutations, bounding "
                f"boxes, citations.\nDiagnosis: {state['consensus']}\nNotes: {notes}\n"
                'Return JSON {"text": str}.'
            ),
            {"text": "unavailable"},
        )
        patient = _parse(
            llm.complete(
                "Patient view: compassionate simplified explanation of findings "
                f"and next steps.\nDiagnosis: {state['consensus']}\nNotes: {notes}\n"
                'Return JSON {"text": str}.'
            ),
            {"text": "unavailable"},
        )
        clinician_text = clinician.get("text", "")
        return {
            "explain": {"clinician": clinician_text, "patient": patient.get("text", "")},
            "status": "completed",
            "events": [
                {
                    "type": "agent_step",
                    "node": "explain",
                    "status": "completed",
                    "detail": clinician_text,
                }
            ],
        }

    def after_evidence(state: CaseState) -> str:
        if state["debate_rounds"] < 3 and _conflict(state):
            return "debate"
        return "consensus"

    def after_debate(state: CaseState) -> str:
        if state["debate_rounds"] < 3 and _conflict(state):
            return "debate"
        return "consensus"

    def after_critic(state: CaseState) -> str:
        if state["warnings"] and state["critic_rounds"] <= 1:
            return "debate"
        return "explain"

    g = StateGraph(CaseState)
    for name in AGENT_NODES:
        g.add_node(name, make_agent_node(name))
    g.add_node("rag_evidence", rag_evidence)
    g.add_node("evidence_verify", evidence_verify)
    g.add_node("debate", debate)
    g.add_node("consensus", consensus)
    g.add_node("self_critic", self_critic)
    g.add_node("explain", explain)

    g.add_conditional_edges(START, fan_out, AGENT_NODES + ("rag_evidence",))
    for name in AGENT_NODES:
        g.add_edge(name, "rag_evidence")
    g.add_edge("rag_evidence", "evidence_verify")
    g.add_conditional_edges(
        "evidence_verify", after_evidence, ["debate", "consensus"]
    )
    g.add_conditional_edges("debate", after_debate, ["debate", "consensus"])
    g.add_edge("consensus", "self_critic")
    g.add_conditional_edges(
        "self_critic", after_critic, ["debate", "explain"]
    )
    g.add_edge("explain", END)
    return g.compile()


def _initial_state(case, routing: RoutingMap) -> CaseState:
    return {
        "case": {
            "patient_ref": case.patient_ref,
            "modalities": list(case.modalities),
            "clinical_notes": case.clinical_notes,
            "metadata": dict(case.metadata),
        },
        "routing": asdict(routing),
        "reports": {},
        "events": [],
        "evidence": [],
        "warnings": [],
        "debate_rounds": 0,
        "critic_rounds": 0,
        "consensus": {},
        "explain": {},
        "status": "running",
    }


async def run_case(
    case: Any, llm=None, guard=None, router=None, rag=None, on_event=None
) -> CaseState:
    from app.llm import get_llm
    from app.pii import get_pii_guard

    llm = llm or get_llm()
    guard = guard if guard is not None else get_pii_guard()
    routing = route_case(case, router)
    graph = build_graph(GuardedLLM(llm, guard), rag=rag)
    final = _initial_state(case, routing)
    seen = 0
    async for st in graph.astream(
        final, {"recursion_limit": 40}, stream_mode="values"
    ):
        final = st
        for ev in st["events"][seen:]:
            if on_event is not None:
                on_event(ev)
        seen = len(st["events"])
    final["status"] = "completed"
    return final


__all__ = ["run_case", "build_graph", "CaseState"]
