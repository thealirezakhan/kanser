"""Planning Agent (System 1.5): picks which specialist agents and tools to invoke."""

import json
from dataclasses import dataclass

from app.prompt_guard import wrap_untrusted
from app.schemas import CaseInput
from app.system1 import RoutingMap

_AGENT_MODALITY = {
    "radiology": "imaging",
    "pathology": "pathology",
    "genomics": "genomics",
    "clinical": "notes/labs",
}

_ALL_TOOLS = {"rag", "vision", "vcf_parser", "labs_parser", "notes_parser"}


@dataclass(frozen=True)
class Plan:
    agents: tuple[str, ...]
    tools: tuple[str, ...]
    reasons: tuple[str, ...]
    provider: str


def _heuristic(case: CaseInput, routing: RoutingMap) -> Plan:
    tools = ["rag"]
    mods = set(case.modalities)
    if mods & {"ct", "cxr"}:
        tools.append("vision")
    if "genomics" in mods:
        tools.append("vcf_parser")
    if "labs" in mods:
        tools.append("labs_parser")
    if "notes" in mods:
        tools.append("notes_parser")
    reasons = [
        f"{a} dropped: no {_AGENT_MODALITY[a]} data"
        for a in routing.dropped
        if a in _AGENT_MODALITY
    ] or ["all modalities present"]
    return Plan(
        agents=tuple(routing.activated),
        tools=tuple(tools),
        reasons=tuple(reasons),
        provider="heuristic",
    )


def _parse(raw: str) -> dict | None:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def build_plan(case: CaseInput, routing: RoutingMap, llm=None) -> Plan:
    if llm is not None:
        prompt = (
            "Planning agent: decide which specialist agents and tools this case "
            "needs. Only agents supported by available modalities may be chosen. "
            'Return JSON {"agents": [str], "tools": [str], "reasons": [str]}.\n'
            f"Modalities: {list(case.modalities)}\n"
            f"Notes: {wrap_untrusted(case.clinical_notes[:500])}\n"
            f"Allowed agents: {list(routing.activated)}"
        )
        data = _parse(llm.complete(prompt))
        if data is not None:
            allowed = set(routing.activated)
            agents = tuple(
                a for a in data.get("agents", []) if isinstance(a, str) and a in allowed
            )
            tools = tuple(
                t
                for t in data.get("tools", [])
                if isinstance(t, str) and t in _ALL_TOOLS
            )
            reasons = tuple(str(r) for r in data.get("reasons", [])) or (
                "llm plan accepted",
            )
            if agents:
                return Plan(agents=agents, tools=tools, reasons=reasons, provider="llm")
    return _heuristic(case, routing)
