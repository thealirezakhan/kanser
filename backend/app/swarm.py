import json
from dataclasses import asdict, replace
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.claims import gate_clinician_text, sanitize_literature
from app.planner import build_plan
from app.prompt_guard import wrap_untrusted
from app.system1 import RoutingMap, route_case


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


def _concat(a: list, b: list) -> list:
    return list(a) + list(b)


class CaseState(TypedDict):
    case: dict
    routing: dict
    plan: dict
    standardized: dict
    reports: Annotated[dict, _merge]
    events: Annotated[list, _concat]
    # plain list: evidence_verify REPLACES rag_evidence output, no concat
    evidence: list
    warnings: Annotated[list, _concat]
    guideline: dict
    debate_rounds: int
    critic_rounds: int
    consensus: dict
    explain: dict
    status: str


AGENT_NODES = ("radiology", "pathology", "genomics", "clinical")

# confirmatory artifact each agent wants; absent => missing_flags entry
_AGENT_EXPECTS = {
    "radiology": ("dicom_scan", "imaging_findings"),
    "pathology": ("slide_image", "slide"),
    "genomics": ("vcf_file", "vcf"),
    "clinical": ("labs_panel", "labs"),
}

_FUSION_WEIGHTS = {"radiology": 0.3, "pathology": 0.3, "clinical": 0.25, "genomics": 0.15}


def _missing_flags(name: str, modalities: list, metadata: dict) -> list[str]:
    label, key = _AGENT_EXPECTS[name]
    if metadata.get(key):
        return []
    if key in modalities:
        return []
    return [label]


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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _calibrate(reports: dict, evidence: list) -> dict:
    """Confidence-weighted overall score with missing-modality penalties."""
    per_agent = {name: float(r["confidence"]) for name, r in reports.items()}
    weights = {n: _FUSION_WEIGHTS.get(n, 0.1) for n in per_agent}
    total_w = sum(weights.values()) or 1.0
    overall = sum(per_agent[n] * weights[n] for n in per_agent) / total_w
    missing = sorted({f for r in reports.values() for f in r.get("missing_flags", [])})
    overall -= 0.05 * len(missing)
    overall = max(0.01, min(0.99, overall))
    reason = (
        f"missing: {', '.join(missing)}" if missing else "all expected modalities present"
    )
    if evidence:
        reason += f"; {len(evidence)} verified citations"
    return {
        "per_agent": per_agent,
        "overall": round(overall, 3),
        "reason": reason,
        "missing": missing,
    }


def build_graph(llm, rag=None):
    from app.rag import build_query, filter_evidence

    def fan_out(state: CaseState) -> list[str]:
        activated = [a for a in state["routing"]["activated"] if a in AGENT_NODES]
        return activated or ["rag_evidence"]

    def make_agent_node(name: str):
        async def node(state: CaseState) -> dict:
            modalities = state["case"]["modalities"]
            metadata = state["case"].get("metadata", {})
            missing = _missing_flags(name, modalities, metadata)
            prompt = (
                f"role: {name}\n"
                "Analyze this lung cancer case. Return JSON "
                '{"hypothesis": str, "confidence": float}.\n'
                f"Modalities available: {modalities}\n"
                f"Missing data for this specialty: {missing}\n"
                f"Clinical notes: {wrap_untrusted(state['case'].get('clinical_notes', ''))}"
            )
            data = _parse(
                llm.complete(prompt),
                {"hypothesis": "unparsed output", "confidence": 0.5},
            )
            report = {
                "agent": name,
                "hypothesis": str(data.get("hypothesis", ""))[:2000],
                "confidence": float(data.get("confidence", 0.5)),
                "missing_flags": missing,
            }
            detail = report["hypothesis"]
            if missing:
                detail += f" | missing: {', '.join(missing)}"
            return {
                "reports": {name: report},
                "events": [
                    {"type": "agent_step", "node": name, "status": "started"},
                    {
                        "type": "agent_step",
                        "node": name,
                        "status": "completed",
                        "confidence": report["confidence"],
                        "detail": detail,
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
        relevance_dropped = 0
        if kept:
            prompt = (
                "Relevance check: drop citations that do not support or contradict "
                "the agent hypotheses. Return JSON {\"drop\": [id]} for irrelevant "
                "citations only.\n"
                + json.dumps(
                    {"citations": {h["id"]: wrap_untrusted(h["text"][:300]) for h in kept}}
                )
                + "\n"
                + json.dumps(
                    {
                        "hypotheses": {
                            k: v["hypothesis"]
                            for k, v in state["reports"].items()
                        }
                    }
                )
            )
            verdict = _parse(llm.complete(prompt), {"drop": []})
            drop_ids = {str(x) for x in verdict.get("drop", [])}
            remaining = [h for h in kept if h["id"] not in drop_ids]
            relevance_dropped = len(kept) - len(remaining)
            kept = remaining
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
                "dropped": len(dropped) + relevance_dropped,
                "detail": (
                    f"kept {len(kept)}; stale/contradicted {len(dropped)}; "
                    f"irrelevant {relevance_dropped}"
                ),
            },
        ]
        return {"evidence": kept, "events": events}

    async def fusion_stages(state: CaseState) -> dict:
        """Staged multi-level fusion: image -> clinical -> knowledge scores."""
        reports = state["reports"]
        image = [r["confidence"] for n, r in reports.items() if n == "radiology"]
        clinical = [
            r["confidence"]
            for n, r in reports.items()
            if n in ("clinical", "pathology", "genomics")
        ]
        knowledge = [float(h.get("score", 0.0)) for h in state["evidence"]]
        stages = {
            "fusion_image": _mean(image),
            "fusion_clinical": _mean(clinical),
            "fusion_knowledge": _mean(knowledge),
        }
        events = [
            {
                "type": "agent_step",
                "node": node,
                "status": "completed",
                "confidence": round(score, 3),
                "detail": f"stage score={score:.3f}",
            }
            for node, score in stages.items()
        ]
        return {"events": events, "reports": reports}

    async def consensus(state: CaseState) -> dict:
        reports = state["reports"]
        stages = {
            "image": _mean(
                [r["confidence"] for n, r in reports.items() if n == "radiology"]
            ),
            "clinical": _mean(
                [
                    r["confidence"]
                    for n, r in reports.items()
                    if n in ("clinical", "pathology", "genomics")
                ]
            ),
            "knowledge": _mean([float(h.get("score", 0.0)) for h in state["evidence"]]),
        }
        prompt = (
            "Consensus: resolve via confidence-weighted reasoning, not majority vote. "
            "Consider the staged fusion scores (image, clinical, knowledge). "
            'Return JSON {"diagnosis": str, "confidence": float}.\n'
            + json.dumps(
                {
                    "reports": {k: v["hypothesis"] for k, v in reports.items()},
                    "missing_flags": sorted(
                        {f for r in reports.values() for f in r["missing_flags"]}
                    ),
                    "fusion_stages": stages,
                    "evidence": [
                        {**h, "text": wrap_untrusted(str(h.get("text", ""))[:500])}
                        for h in state["evidence"]
                    ],
                }
            )
        )
        data = _parse(
            llm.complete(prompt), {"diagnosis": "unresolved", "confidence": 0.0}
        )
        raw_conf = float(data.get("confidence", 0.0))
        calibration = _calibrate(reports, state["evidence"])
        from app.abstention import derive_diagnosis_state, evaluate_abstention

        abstain = evaluate_abstention(
            case=state["case"],
            evidence=state["evidence"],
            diagnosis=str(data.get("diagnosis", "")),
        )
        consensus_out = {
            "diagnosis": str(data.get("diagnosis", "")),
            "confidence": 0.0 if abstain else calibration["overall"],
            "llm_confidence": raw_conf,
            "fusion_stages": stages,
            "calibration": calibration,
            "abstain": abstain,
            "diagnosis_state": derive_diagnosis_state(
                state["case"].get("modalities", []), abstain
            ),
        }
        detail = (
            f"ABSTAINED: {abstain['reason']}"
            if abstain
            else (
                f"{consensus_out['diagnosis']} "
                f"({calibration['overall']:.2f}) | {calibration['reason']}"
            )
        )
        return {
            "consensus": consensus_out,
            "events": [
                {
                    "type": "agent_step",
                    "node": "consensus",
                    "status": "completed",
                    "confidence": consensus_out["confidence"],
                    "detail": detail,
                },
                {
                    "type": "calibration",
                    "per_agent": calibration["per_agent"],
                    "overall": consensus_out["confidence"],
                    "reason": calibration["reason"],
                },
            ],
        }

    async def self_critic(state: CaseState) -> dict:
        prompt = (
            "Self-critic: what alternative conditions (granuloma, pneumonia, ...) could "
            "mimic these findings? Check guideline alignment (NCCN). "
            'Return JSON {"warnings": [str], "guideline": {"aligned": bool, "note": str}}.\n'
            + json.dumps(
                {
                    "diagnosis": state["consensus"].get("diagnosis", ""),
                    "reports": {
                        k: v["hypothesis"] for k, v in state["reports"].items()
                    },
                }
            )
        )
        data = _parse(
            llm.complete(prompt),
            {"warnings": [], "guideline": {"aligned": True, "note": ""}},
        )
        warnings = [str(w) for w in data.get("warnings", [])]
        guideline = data.get("guideline") or {}
        aligned = bool(guideline.get("aligned", True))
        note = str(guideline.get("note", ""))
        if not aligned and note:
            warnings.append(f"guideline discrepancy: {note}")
        return {
            "warnings": warnings,
            "guideline": {"aligned": aligned, "note": note},
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
        notes = wrap_untrusted(state["case"].get("clinical_notes", ""))
        evidence_ids = [h["id"] for h in state["evidence"][:5]]
        clinician = _parse(
            llm.complete(
                "Clinician view: technical breakdown with gene mutations, bounding "
                f"boxes, citations.\nDiagnosis: {state['consensus']}\nNotes: {notes}\n"
                'Return JSON {"text": str, "alternatives": [str], "reasons": [str], '
                '"literature": [str]}.'
            ),
            {"text": "unavailable", "alternatives": [], "reasons": [], "literature": []},
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
        alternatives = [str(a) for a in clinician.get("alternatives", [])][:5]
        reasons = [str(r) for r in clinician.get("reasons", [])][:8]
        literature = sanitize_literature(
            [str(x) for x in clinician.get("literature", [])][:8],
            allowed_ids=set(evidence_ids),
        )
        from app.vision import VISION_RAN

        clinician_text = gate_clinician_text(
            clinician_text,
            modalities=state["case"].get("modalities", []),
            vision_ran=VISION_RAN,
        )
        explain_out = {
            "clinician": clinician_text,
            "patient": patient.get("text", ""),
            "alternatives": alternatives,
            "reasons": reasons,
            "literature": literature,
        }
        return {
            "explain": explain_out,
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
    g.add_node("fusion_stages", fusion_stages)
    g.add_node("debate", debate_node(llm))
    g.add_node("consensus", consensus)
    g.add_node("self_critic", self_critic)
    g.add_node("explain", explain)

    g.add_conditional_edges(START, fan_out, AGENT_NODES + ("rag_evidence",))
    for name in AGENT_NODES:
        g.add_edge(name, "rag_evidence")
    g.add_edge("rag_evidence", "evidence_verify")
    g.add_edge("evidence_verify", "fusion_stages")
    g.add_conditional_edges(
        "fusion_stages", after_evidence, ["debate", "consensus"]
    )
    g.add_conditional_edges("debate", after_debate, ["debate", "consensus"])
    g.add_edge("consensus", "self_critic")
    g.add_conditional_edges(
        "self_critic", after_critic, ["debate", "explain"]
    )
    g.add_edge("explain", END)
    return g.compile()


def debate_node(llm):
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

    return debate


def _initial_state(case, routing: RoutingMap, plan: dict) -> CaseState:
    plan_event = {
        "type": "plan",
        "node": "planner",
        "agents": plan.get("agents", []),
        "tools": plan.get("tools", []),
        "reasons": plan.get("reasons", []),
        "provider": plan.get("provider", ""),
        "detail": "invoke: " + ", ".join(plan.get("agents", [])),
    }
    return {
        "case": {
            "patient_ref": case.patient_ref,
            "modalities": list(case.modalities),
            "clinical_notes": case.clinical_notes,
            "metadata": dict(case.metadata),
        },
        "routing": asdict(routing),
        "plan": plan,
        "standardized": {},
        "reports": {},
        "events": [plan_event],
        "evidence": [],
        "warnings": [],
        "guideline": {},
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
    guarded = GuardedLLM(llm, guard)
    plan = build_plan(case, routing, llm=guarded)
    if plan.agents:
        activated = tuple(dict.fromkeys(plan.agents))
        all_agents = tuple(dict.fromkeys(routing.activated + routing.dropped))
        routing = replace(
            routing,
            activated=activated,
            dropped=tuple(a for a in all_agents if a not in activated),
        )
    graph = build_graph(guarded, rag=rag)
    final = _initial_state(case, routing, asdict_plan(plan))
    # Data Standardization Agent runs first (new.md: standardize -> plan -> agents)
    from app.standardize import standardize_case

    std = standardize_case(case.model_dump())
    std_event = {
        "type": "standardize",
        "node": "standardization",
        "schema_version": std["schema_version"],
        "quality_flags": std["quality_flags"],
        "detail": (
            f"schema {std['schema_version']}; "
            f"{len(std['quality_flags'])} quality flags"
        ),
    }
    final["standardized"] = std
    # System 1 orchestration rationale: pathway, readiness gates, inference limits
    from app.system1 import assess_case

    assess = assess_case(case, router)
    s1_event = {
        "type": "system1",
        "node": "system1",
        "pathway": assess.pathway,
        "must_not_infer": assess.must_not_infer,
        "recommended": assess.readiness["recommended_tests"],
        "detail": (
            f"system1 pathway={assess.pathway}; "
            f"{assess.readiness['system_status']}; risk={assess.routing.risk_grade}; gates: "
            + ", ".join(
                f"{name}={'ready' if pw['ready'] else 'blocked'}"
                for name, pw in assess.readiness["pathways"].items()
            )
        ),
    }
    final["events"] = [std_event, s1_event, *final["events"]]
    final["warnings"] = [
        *final["warnings"],
        *(f"{f['code']}: {f['message']}" for f in std["quality_flags"]),
    ]
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


def asdict_plan(plan) -> dict:
    return {
        "agents": plan.agents,
        "tools": plan.tools,
        "reasons": plan.reasons,
        "provider": plan.provider,
    }


__all__ = ["run_case", "build_graph", "CaseState"]
