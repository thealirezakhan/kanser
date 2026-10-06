import statistics
import time

from app.schemas import CaseInput
from app.system1 import HeuristicRouter, RoutingMap, route_case


def _case(modalities, notes=""):
    return CaseInput(patient_ref="t", modalities=modalities, clinical_notes=notes)


def test_routing_map_shape():
    rm = route_case(_case(["ct"], notes="nodule found"), HeuristicRouter())
    assert isinstance(rm, RoutingMap)
    assert rm.provider == "heuristic"
    assert rm.latency_ms >= 0
    assert rm.risk_grade in {"low", "medium", "high"}
    assert 1 <= rm.priority <= 3


def test_missing_genomics_dropped_even_if_requested():
    rm = HeuristicRouter().route(_case(["ct", "labs"]))
    assert "genomics" in rm.dropped
    assert "genomics" not in rm.activated


def test_genomics_present_activates_genomics():
    rm = HeuristicRouter().route(_case(["ct", "genomics"]))
    assert "genomics" in rm.activated


def test_no_imaging_drops_radiology():
    rm = HeuristicRouter().route(_case(["labs", "notes"], notes="cough"))
    assert "radiology" in rm.dropped


def test_pathology_only_when_pathology_modality_present():
    rm = HeuristicRouter().route(_case(["ct"]))
    assert "pathology" in rm.dropped
    rm = HeuristicRouter().route(_case(["ct", "pathology"]))
    assert "pathology" in rm.activated


def test_high_risk_keywords_raise_priority():
    rm = HeuristicRouter().route(
        _case(["ct"], notes="metastatic disease, stage IV adenocarcinoma")
    )
    assert rm.risk_grade == "high"
    assert rm.priority == 1


def test_low_risk_default():
    rm = HeuristicRouter().route(_case(["ct"], notes="small stable nodule"))
    assert rm.risk_grade in {"low", "medium"}
    assert rm.priority >= 2


def test_heuristic_p95_under_50ms():
    cases = [_case(["ct", "genomics"], notes="nodule") for _ in range(1000)]
    router = HeuristicRouter()
    latencies = []
    for c in cases:
        t0 = time.perf_counter()
        router.route(c)
        latencies.append((time.perf_counter() - t0) * 1000)
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    assert p95 < 50, f"p95={p95:.1f}ms exceeds 50ms budget"
    assert statistics.median(latencies) < 10


def test_fallback_when_router_raises():
    class BoomRouter:
        name = "boom"

        def route(self, case):
            raise RuntimeError("provider down")

    rm = route_case(_case(["ct"]), BoomRouter())
    assert rm.provider == "heuristic"
    assert "radiology" in rm.activated


def _laya_answers(**over):
    base = {
        "radiology_focus": {"choice": "advanced_staging", "confidence": 0.9},
        "care_pathway": {"choice": "outpatient_workup", "confidence": 0.9},
        "risk": {"choice": "medium", "confidence": 0.85},
        "molecular_urgency": {"noul": 0.2, "confidence": 0.9},
        "tumor_board": {"noul": 0.3, "confidence": 0.9},
        "tissue_required": {"noul": 0.8, "confidence": 0.9},
        "clinical_acuity": {"score": 1.0, "confidence": 0.9},
    }
    base.update(over)
    return {"answers": base}


class _FakeLaya:
    def __init__(self, payload):
        self._payload = payload
        self.state = None
        self.questions = None

    def predict(self, state, questions):
        self.state = state
        self.questions = questions
        return self._payload


def test_laya_router_mocked_answers():
    from app.system1 import LayaRouter

    fake = _FakeLaya(_laya_answers())
    router = LayaRouter(agent=fake)
    rm = router.route(_case(["ct", "pathology"]))
    # Laya can keep/drop what data allows; presence rules still hard-override
    assert "radiology" in rm.activated
    assert "pathology" in rm.activated
    assert "genomics" in rm.dropped, "low molecular urgency + no genomics data"
    assert rm.provider == "laya"
    assert rm.risk_grade == "medium"
    assert rm.needs_human_review is False
    assert rm.tumor_board is False
    # rich question matrix is in play, not the old 4 binary probes
    assert set(fake.questions) >= {
        "radiology_focus",
        "care_pathway",
        "risk",
        "molecular_urgency",
        "tumor_board",
        "tissue_required",
        "clinical_acuity",
    }


def test_laya_state_packs_rich_intake_payload():
    from app.schemas import Intake
    from app.system1 import LayaRouter

    intake = Intake(
        age=64,
        sex="male",
        reason_for_presentation="Staging after CT",
        encounter="staging",
        pack_years=40,
        smoking_status="current",
        symptoms=[{"name": "hemoptysis", "state": "present"}],
        imaging=["ct_chest", "pet_ct"],
        comorbidities=["COPD"],
        ecog=2,
    )
    case = CaseInput(
        patient_ref="t",
        modalities=["ct", "notes"],
        clinical_notes="mass on CT",
        intake=intake,
    )
    fake = _FakeLaya(_laya_answers())
    LayaRouter(agent=fake).route(case)
    st = fake.state
    assert st["pack_years"] == 40
    assert st["encounter"] == "staging"
    assert st["comorbidities"] == ["COPD"]
    assert st["ecog"] == 2
    assert st["symptoms"][0]["name"] == "hemoptysis"
    assert st["symptoms"][0]["state"] == "present"
    assert st["smoking_status"] == "current"
    assert st["clinical_notes"] == "mass on CT"
    assert st["modalities"] == ["ct", "notes"]


def test_laya_low_confidence_flags_human_review():
    from app.system1 import HITL_CONFIDENCE_THRESHOLD, LayaRouter

    assert HITL_CONFIDENCE_THRESHOLD == 0.70
    low = _FakeLaya(_laya_answers(**{"risk": {"choice": "high", "confidence": 0.45}}))
    rm = LayaRouter(agent=low).route(_case(["ct", "pathology"]))
    assert rm.needs_human_review is True, "confidence below threshold forces HITL"
    ok = _FakeLaya(_laya_answers())
    rm2 = LayaRouter(agent=ok).route(_case(["ct", "pathology"]))
    assert rm2.needs_human_review is False


def test_laya_missing_tissue_with_high_need_flags_review():
    from app.system1 import LayaRouter

    fake = _FakeLaya(_laya_answers(**{"tissue_required": {"noul": 0.9, "confidence": 0.95}}))
    rm = LayaRouter(agent=fake).route(_case(["ct"]))  # no pathology upload
    assert rm.needs_human_review is True, "needs tissue but no slides uploaded"
    rm2 = LayaRouter(agent=fake).route(_case(["ct", "pathology"]))
    assert rm2.needs_human_review is False


def test_laya_tumor_board_flag_from_semantic_score():
    from app.system1 import LayaRouter

    complex_case = _FakeLaya(
        _laya_answers(**{"tumor_board": {"noul": 0.7, "confidence": 0.8}})
    )
    assert LayaRouter(agent=complex_case).route(_case(["ct"])).tumor_board is True
    simple = _FakeLaya(_laya_answers())
    assert LayaRouter(agent=simple).route(_case(["ct"])).tumor_board is False


def test_laya_acuity_reweights_risk_and_urgency_sets_priority():
    from app.system1 import LayaRouter

    fake = _FakeLaya(
        _laya_answers(
            **{
                "risk": {"choice": "low", "confidence": 0.9},
                "clinical_acuity": {"score": 3.6, "confidence": 0.9},
            }
        )
    )
    rm = LayaRouter(agent=fake).route(_case(["ct"]))
    assert rm.risk_grade == "medium", "high acuity bumps a low semantic risk grade"
    urgent = _FakeLaya(
        _laya_answers(
            **{
                "risk": {"choice": "low", "confidence": 0.9},
                "clinical_acuity": {"score": 1.0, "confidence": 0.9},
                "care_pathway": {"choice": "urgent_oncology", "confidence": 0.9},
            }
        )
    )
    assert LayaRouter(agent=urgent).route(_case(["ct"])).priority == 1


def test_route_case_forwards_hitl_fields():
    from app.system1 import LayaRouter

    fake = _FakeLaya(_laya_answers(**{"risk": {"choice": "high", "confidence": 0.5}}))
    rm = route_case(_case(["ct"]), LayaRouter(agent=fake))
    assert rm.needs_human_review is True
    assert rm.tumor_board is False
    assert rm.provider == "laya"
    assert rm.latency_ms >= 0
