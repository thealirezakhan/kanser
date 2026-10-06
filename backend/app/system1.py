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
    needs_human_review: bool = False
    tumor_board: bool = False


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


# Confidence-driven HITL: below this aggregate answer confidence the case is
# flagged for mandatory clinician review instead of autonomous routing.
HITL_CONFIDENCE_THRESHOLD = 0.70

_ACUITY_REWEIGHT = 3.0  # clinical_acuity score (0..4) that bumps low risk to medium
_URGENT_PATHWAYS = {"urgent_pulmonology", "urgent_oncology"}


class LayaRouter:
    """Semantic clinical triage over unstructured text via Laya.

    File presence stays a Python set lookup (_apply_presence). Laya decides
    what the files *mean*: radiology depth, risk grade, care pathway urgency,
    molecular urgency, MDT necessity, tissue need, acuity — from the full
    intake payload, in one sub-50ms-class forward pass on GPU/quantized runs.
    """

    name = "laya"

    _QUESTIONS = {
        "radiology_focus": {
            "type": "choice",
            "instructions": (
                "Determine the required depth of radiological analysis from "
                "`clinical_notes` and the clinical picture in `state`."
            ),
            "criteria": {
                "standard_screening": (
                    "Routine nodule tracking or minor incidental findings."
                ),
                "advanced_staging": (
                    "Suspected primary malignancy requiring precise tumor sizing, "
                    "lymph node involvement, or metastasis evaluation."
                ),
                "skip": "No relevant imaging or completely normal historical scan.",
            },
        },
        "care_pathway": {
            "type": "choice",
            "instructions": (
                "Triage the case: does it need urgent intervention or can it wait "
                "for outpatient workup, based on symptoms and narrative?"
            ),
            "criteria": {
                "urgent_pulmonology": (
                    "Airway compromise, massive hemoptysis, post-obstructive "
                    "complications needing urgent pulmonology."
                ),
                "urgent_oncology": (
                    "Rapidly progressive or symptomatic advanced disease needing "
                    "urgent oncology start."
                ),
                "outpatient_workup": (
                    "Stable presentation routed to standard outpatient diagnostic "
                    "workup."
                ),
                "surveillance": "Known stable disease on routine follow-up.",
            },
        },
        "risk": {
            "type": "choice",
            "instructions": "Assess overall clinical risk grade for prioritization.",
            "criteria": {
                "low": "Stable, benign, or low-suspicion findings.",
                "medium": "Suspicious findings requiring active diagnostic workup.",
                "high": (
                    "Aggressive, metastatic, or advanced-stage disease requiring "
                    "urgent escalation."
                ),
            },
        },
        "molecular_urgency": {
            "type": "noul",
            "instructions": (
                "Is urgent genomic/molecular profiling (EGFR, ALK, ROS1, PD-L1) "
                "critical for this case's immediate treatment pathway?"
            ),
        },
        "tumor_board": {
            "type": "noul",
            "instructions": (
                "Does this case present complex staging, conflicting comorbidities, "
                "or high-risk features requiring a multidisciplinary tumor board debate?"
            ),
        },
        "tissue_required": {
            "type": "noul",
            "instructions": (
                "Does this case require tissue histology before any treatment "
                "decision can be made?"
            ),
        },
        "clinical_acuity": {
            "type": "score",
            "instructions": "How acute is the clinical presentation right now?",
            "criteria": [
                "asymptomatic or incidental finding only",
                "mild, stable symptoms",
                "new or worsening symptoms",
                "systemic symptoms such as weight loss, fever, or night sweats",
                "acute or organ-threatening presentation",
            ],
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

    @staticmethod
    def _state(case: CaseInput) -> dict:
        """Rich multimodal payload: full intake picture, not just file names."""
        raw = getattr(case, "intake", None)
        if raw is None:
            intake: dict = {}
        elif hasattr(raw, "model_dump"):
            intake = raw.model_dump()
        else:
            intake = dict(raw)
        return {
            "clinical_notes": case.clinical_notes,
            "modalities": list(case.modalities),
            "metadata": case.metadata,
            "patient_ref": case.patient_ref,
            "encounter": intake.get("encounter", ""),
            "age": intake.get("age"),
            "sex": intake.get("sex", ""),
            "symptoms": intake.get("symptoms", []),
            "smoking_status": intake.get("smoking_status", "unknown"),
            "pack_years": intake.get("pack_years"),
            "exposures": intake.get("exposures", []),
            "comorbidities": intake.get("comorbidities", []),
            "prior_cancer": intake.get("prior_cancer", False),
            "imaging": intake.get("imaging", []),
            "tissue_status": intake.get("tissue_status", "unknown"),
            "histology": intake.get("histology", ""),
            "mediastinal": intake.get("mediastinal", "unknown"),
            "molecular_status": intake.get("molecular_status", "unknown"),
            "ecog": intake.get("ecog"),
            "fev1_pct": intake.get("fev1_pct"),
            "dlco_pct": intake.get("dlco_pct"),
        }

    @staticmethod
    def _confidence(answers: dict) -> float:
        """Aggregate gate: the most uncertain single answer governs."""
        confs = [
            float(a.get("answer_confidence", a.get("confidence", 1.0)))
            for a in answers.values()
            if isinstance(a, dict)
        ]
        return min(confs) if confs else 1.0

    def route(self, case: CaseInput) -> RoutingMap:
        result = self.agent.predict(self._state(case), self._QUESTIONS)
        answers = result.get("answers", {})

        rad_focus = answers.get("radiology_focus", {}).get("choice", "skip")
        mol = float(answers.get("molecular_urgency", {}).get("noul", 0.0))
        mdt = float(answers.get("tumor_board", {}).get("noul", 0.0))
        tissue_need = float(answers.get("tissue_required", {}).get("noul", 0.0))
        acuity = float(answers.get("clinical_acuity", {}).get("score", 0.0))
        pathway = answers.get("care_pathway", {}).get("choice", "outpatient_workup")

        mods = set(case.modalities)
        wanted = {
            "radiology": rad_focus != "skip" and bool(mods),
            "pathology": "pathology" in mods or rad_focus == "advanced_staging",
            "genomics": mol >= 0.6 or "genomics" in mods,
            "clinical": True,
        }
        activated, dropped = _apply_presence(wanted, mods)

        grade = answers.get("risk", {}).get("choice", "medium")
        if grade not in {"low", "medium", "high"}:
            grade = "medium"
        if grade == "low" and acuity >= _ACUITY_REWEIGHT:
            grade = "medium"
        priority = {"high": 1, "medium": 2, "low": 3}[grade]
        if pathway in _URGENT_PATHWAYS:
            priority = 1

        confidence = self._confidence(answers)
        needs_review = confidence < HITL_CONFIDENCE_THRESHOLD or (
            tissue_need >= 0.7 and "pathology" not in mods
        )
        return RoutingMap(
            activated=activated,
            dropped=dropped,
            risk_grade=grade,
            priority=priority,
            provider=self.name,
            latency_ms=0.0,
            confidence=round(confidence, 3),
            needs_human_review=needs_review,
            tumor_board=mdt >= 0.5,
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
        needs_human_review=rm.needs_human_review,
        tumor_board=rm.tumor_board,
    )


_PATHWAYS = {
    "new_suspected": "diagnostic",
    "newly_diagnosed": "diagnostic",
    "second_opinion": "diagnostic",
    "recurrence": "diagnostic",
    "staging": "staging",
    "treatment_response": "staging",
    "treatment_planning": "treatment",
    "surveillance": "surveillance",
}

_SKIP_REASON = {
    "radiology": "no imaging modality on case",
    "pathology": "no pathology data on case",
    "genomics": "no genomic data on case",
    "clinical": "no clinical notes or labs on case",
}


def pathway_for(encounter: str) -> str:
    return _PATHWAYS.get(encounter, "diagnostic")


@dataclass(frozen=True)
class Assessment:
    """System 1 fast clinical orchestration output: what exists, what is missing,
    which agents run, and what must not be inferred."""

    pathway: str
    readiness: dict
    routing: RoutingMap
    agents_skipped: dict[str, str]
    must_not_infer: list[str]
    diagnostic_state: dict
    tnm: dict
    contradictions: list


def _intake_dict(case) -> dict:
    raw = getattr(case, "intake", None)
    if raw is None:
        return {}
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    return dict(raw)


def _must_not_infer(intake: dict) -> list[str]:
    imaging = set(intake.get("imaging", []))
    not_performed = set(intake.get("not_performed", []))
    out: list[str] = []
    if "pet_ct" not in imaging:
        why = "assessed: not performed" if "pet_ct" in not_performed else "not yet assessed"
        out.append(f"No PET/CT ({why}) — do not assign M stage")
    if intake.get("tissue_status") not in {"histology_available", "surgical_specimen"}:
        out.append("No confirmed histology — do not state tumor type or grade")
    if intake.get("molecular_status", "unknown") != "complete":
        out.append("Molecular testing incomplete — do not infer actionable mutations")
    if intake.get("ecog") is None:
        out.append("No ECOG recorded — do not recommend a treatment regimen")
    if intake.get("mediastinal", "unknown") != "assessed":
        out.append("No mediastinal nodal assessment — do not assign N stage")
    return out


def assess_case(case, router=None, findings: list | None = None) -> Assessment:
    intake = _intake_dict(case)
    modalities = list(getattr(case, "modalities", []) or [])
    from app.readiness import evaluate

    readiness = evaluate(intake, modalities)
    routing = route_case(case, router)
    skipped = {a: _SKIP_REASON.get(a, "required data unavailable") for a in routing.dropped}
    case_dict = case.model_dump() if hasattr(case, "model_dump") else dict(case)
    case_dict["intake"] = intake
    active_findings = [
        f.model_dump() if hasattr(f, "model_dump") else dict(f) for f in (findings or [])
    ]
    from app.conflicts import detect_conflicts
    from app.states import case_state
    from app.tnm import stage_case

    contradictions = detect_conflicts(active_findings)
    tnm = stage_case(case_dict, active_findings)
    if contradictions:
        # conflicting evidence: never present a stage group as established
        tnm = {
            **tnm,
            "stage_group": "Stage indeterminate - insufficient evidence",
            "determinable": False,
            "warnings": tnm["warnings"] + ["contradictory evidence - stage withheld"],
        }
    return Assessment(
        pathway=pathway_for(intake.get("encounter", "new_suspected")),
        readiness=readiness,
        routing=routing,
        agents_skipped=skipped,
        must_not_infer=_must_not_infer(intake),
        diagnostic_state=case_state(case_dict, active_findings, contradictions),
        tnm=tnm,
        contradictions=contradictions,
    )