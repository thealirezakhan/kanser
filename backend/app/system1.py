import os
import re
from dataclasses import dataclass
from time import perf_counter

from app.schemas import CaseInput

_IMAGING = {"ct", "cxr"}
_ALL_AGENTS = ("radiology", "pathology", "genomics", "clinical")

_HIGH_RISK = re.compile(
    r"metasta|stage\s*(iii|iv|4)|stage 4|terminal|widely\s+spread", re.I
)
_MED_RISK = re.compile(
    r"malignan|carcinoma|adenocarcinoma|tumor|tumour|nodule|mass|lesion", re.I
)

# ponytail: CPU Laya measures 193-464ms preloaded; <50ms budget holds on
# heuristic path and GPU Laya only. Upgrade path: CUDA host or ONNX.
LATENCY_BUDGET_MS = 50.0


@dataclass(frozen=True)
class RoutingMap:
    activated: tuple[str, ...]
    dropped: tuple[str, ...]
    risk_grade: str
    priority: int
    provider: str
    latency_ms: float
    confidence: float = 1.0


def _presence_rules(modalities: set[str]) -> dict[str, bool]:
    return {
        "radiology": bool(modalities & _IMAGING),
        "pathology": "pathology" in modalities,
        "genomics": "genomics" in modalities,
        "clinical": bool(modalities & {"labs", "notes"}),
    }


def _risk(notes: str) -> tuple[str, int]:
    if _HIGH_RISK.search(notes):
        return "high", 1
    if _MED_RISK.search(notes):
        return "medium", 2
    return "low", 3


def _apply_presence(
    wanted: dict[str, bool], modalities: set[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    present = _presence_rules(modalities)
    activated = tuple(a for a in _ALL_AGENTS if wanted.get(a) and present[a])
    dropped = tuple(a for a in _ALL_AGENTS if a not in activated)
    return activated, dropped


class HeuristicRouter:
    name = "heuristic"

    def route(self, case: CaseInput) -> RoutingMap:
        mods = set(case.modalities)
        wanted = {a: True for a in _ALL_AGENTS}
        grade, priority = _risk(case.clinical_notes)
        activated, dropped = _apply_presence(wanted, mods)
        return RoutingMap(
            activated=activated,
            dropped=dropped,
            risk_grade=grade,
            priority=priority,
            provider=self.name,
            latency_ms=0.0,
        )


class LayaRouter:
    name = "laya"

    _QUESTIONS = {
        "radiology": {
            "type": "noul",
            "instructions": "Is radiology image analysis required for this case?",
        },
        "pathology": {
            "type": "noul",
            "instructions": "Is pathology slide analysis required for this case?",
        },
        "genomics": {
            "type": "noul",
            "instructions": "Is genomic mutation analysis required for this case?",
        },
        "risk": {
            "type": "choice",
            "instructions": "Clinical risk grade for this case",
            "criteria": {
                "low": "stable or benign findings",
                "medium": "suspicious findings needing workup",
                "high": "aggressive, metastatic, or advanced-stage disease",
            },
        },
    }

    def __init__(self, agent=None) -> None:
        self._agent = agent

    @property
    def agent(self):
        if self._agent is None:
            from laya import Router

            self._agent = Router()
        return self._agent

    def route(self, case: CaseInput) -> RoutingMap:
        state = {
            "modalities": list(case.modalities),
            "clinical_notes": case.clinical_notes,
            "metadata": case.metadata,
        }
        result = self.agent.predict(state, self._QUESTIONS)
        answers = result["answers"]
        wanted = {
            a: bool(answers.get(a, {}).get("noul", 0.0) >= 0.5)
            for a in ("radiology", "pathology", "genomics")
        }
        wanted["clinical"] = True
        mods = set(case.modalities)
        activated, dropped = _apply_presence(wanted, mods)
        grade = answers.get("risk", {}).get("choice", "low")
        if grade not in {"low", "medium", "high"}:
            grade = "low"
        priority = {"high": 1, "medium": 2, "low": 3}[grade]
        confidence = float(answers.get("risk", {}).get("confidence", 1.0))
        return RoutingMap(
            activated=activated,
            dropped=dropped,
            risk_grade=grade,
            priority=priority,
            provider=self.name,
            latency_ms=0.0,
            confidence=confidence,
        )


def get_router():
    provider = os.environ.get("SYSTEM1_PROVIDER", "heuristic").lower()
    if provider == "laya":
        try:
            return LayaRouter()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Laya unavailable, falling back to heuristic", exc_info=True
            )
    return HeuristicRouter()


def route_case(case: CaseInput, router=None) -> RoutingMap:
    router = router or get_router()
    t0 = perf_counter()
    try:
        rm = router.route(case)
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "System 1 provider %s failed, falling back to heuristic",
            getattr(router, "name", "?"),
            exc_info=True,
        )
        rm = HeuristicRouter().route(case)
    latency = (perf_counter() - t0) * 1000
    return RoutingMap(
        activated=rm.activated,
        dropped=rm.dropped,
        risk_grade=rm.risk_grade,
        priority=rm.priority,
        provider=rm.provider,
        latency_ms=round(latency, 3),
        confidence=rm.confidence,
    )
