from app.planner import build_plan
from app.system1 import route_case


class _FakeLlm:
    def __init__(self, out: str) -> None:
        self.out = out
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.out


def _case(modalities, notes="nodule in RUL"):
    from app.schemas import CaseInput

    return CaseInput(patient_ref="P1", modalities=modalities, clinical_notes=notes)


def test_heuristic_plan_drops_missing_modality():
    case = _case(["ct", "notes"])
    routing = route_case(case)
    plan = build_plan(case, routing)
    assert plan.provider == "heuristic"
    assert "genomics" not in plan.agents
    assert "pathology" not in plan.agents
    assert any("genomics" in r for r in plan.reasons)
    assert "rag" in plan.tools
    assert "vision" in plan.tools


def test_heuristic_plan_tools_follow_modalities():
    case = _case(["genomics", "labs", "notes"])
    plan = build_plan(case, route_case(case))
    assert "vcf_parser" in plan.tools
    assert "labs_parser" in plan.tools
    assert "vision" not in plan.tools


def test_llm_plan_validated_against_presence():
    case = _case(["ct", "notes"])
    llm = _FakeLlm(
        '{"agents": ["radiology", "clinical", "pathology"],'
        ' "tools": ["rag"], "reasons": ["image needed"]}'
    )
    plan = build_plan(case, route_case(case), llm=llm)
    assert plan.provider == "llm"
    assert set(plan.agents) == {"radiology", "clinical"}  # pathology rejected
    assert plan.tools == ("rag",)
    assert plan.reasons == ("image needed",)


def test_llm_plan_garbage_falls_back():
    case = _case(["ct"])
    plan = build_plan(case, route_case(case), llm=_FakeLlm("not json"))
    assert plan.provider == "heuristic"
    assert plan.agents == ("radiology",)


def test_plan_serializable():
    case = _case(["ct"])
    plan = build_plan(case, route_case(case))
    d = plan.__dict__
    assert isinstance(d["agents"], tuple)
