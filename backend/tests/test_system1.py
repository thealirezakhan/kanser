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


def test_laya_router_mocked_answers():
    from app.system1 import LayaRouter

    class FakeLaya:
        def predict(self, state, questions):
            return {
                "answers": {
                    "radiology": {"noul": 0.9},
                    "pathology": {"noul": 0.2},
                    "genomics": {"noul": 0.1},
                    "risk": {"choice": "medium", "confidence": 0.8},
                }
            }

    router = LayaRouter(agent=FakeLaya())
    rm = router.route(_case(["ct", "pathology"]))
    # Laya can keep/drop what data allows; presence rules still hard-override
    assert "radiology" in rm.activated
    assert "genomics" in rm.dropped
    assert rm.provider == "laya"
    assert rm.risk_grade == "medium"
