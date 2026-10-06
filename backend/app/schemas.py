from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Modality = Literal["ct", "cxr", "pathology", "genomics", "labs", "notes"]

DataState = Literal["unknown", "assessed", "not_performed", "not_applicable"]

Encounter = Literal[
    "new_suspected",
    "newly_diagnosed",
    "staging",
    "treatment_planning",
    "treatment_response",
    "recurrence",
    "surveillance",
    "second_opinion",
]

TissueStatus = Literal[
    "unknown",
    "no_tissue",
    "biopsy_planned",
    "biopsy_pending",
    "biopsy_performed",
    "cytology_only",
    "histology_available",
    "surgical_specimen",
]

MolecularStatus = Literal[
    "unknown", "not_ordered", "ordered", "pending", "partial", "complete"
]

SymptomState = Literal["unknown", "present", "absent"]


class Symptom(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=1_000)

    name: str = Field(min_length=1, max_length=64)
    state: SymptomState = "unknown"
    duration: str = Field(default="", max_length=64)
    severity: str = Field(default="", max_length=32)


class Biomarker(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=1_000)

    gene: str = Field(min_length=1, max_length=32)
    result: str = Field(default="", max_length=128)
    variant: str = Field(default="", max_length=256)
    method: str = Field(default="", max_length=64)


class Intake(BaseModel):
    """Structured clinical intake. age + sex + reason are the required core;
    imaging, tissue, molecular and staging evidence are all optional."""

    model_config = ConfigDict(extra="forbid", str_max_length=10_000)

    age: int = Field(ge=0, le=130)
    sex: Literal["male", "female", "other", "unknown"]
    reason_for_presentation: str = Field(min_length=1, max_length=2000)
    encounter: Encounter = "new_suspected"
    smoking_status: Literal["never", "former", "current", "unknown"] = "unknown"
    pack_years: float | None = Field(default=None, ge=0, le=1000)
    symptoms: list[Symptom] = Field(default_factory=list, max_length=50)
    exposures: list[str] = Field(default_factory=list, max_length=50)
    imaging: list[str] = Field(default_factory=list, max_length=50)
    not_performed: list[str] = Field(default_factory=list, max_length=50)
    prior_imaging: DataState = "unknown"
    tissue_status: TissueStatus = "unknown"
    tissue_route: str = Field(default="", max_length=64)
    histology: str = Field(default="", max_length=256)
    mediastinal: DataState = "unknown"
    molecular_status: MolecularStatus = "unknown"
    biomarkers: list[Biomarker] = Field(default_factory=list, max_length=50)
    ecog: int | None = Field(default=None, ge=0, le=4)
    fev1_pct: float | None = Field(default=None, ge=0, le=200)
    dlco_pct: float | None = Field(default=None, ge=0, le=200)
    comorbidities: list[str] = Field(default_factory=list, max_length=50)
    prior_cancer: bool = False

    @model_validator(mode="after")
    def _restrict_imaging_to_lung_diagnosis(self) -> "Intake":
        # Lung cancer diagnosis intake only: never brain/whole-body extras
        allowed = {"ct_chest", "pet_ct"}
        unknown = (set(self.imaging) | set(self.not_performed)) - allowed
        if unknown:
            raise ValueError(
                f"imaging fields outside lung cancer diagnosis intake: {sorted(unknown)}"
            )
        return self


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=1_000_000)

    patient_ref: str = Field(min_length=1, max_length=128)
    modalities: list[Modality] = Field(default_factory=list)
    clinical_notes: str = Field(default="", max_length=100_000)
    metadata: dict[str, str] = Field(default_factory=dict)
    intake: Intake | None = None


class CaseOut(BaseModel):
    id: str
    patient_ref: str
    modalities: list[str]
    clinical_notes: str
    metadata: dict[str, str]
    created_at: datetime
    owner: str = ""  # auth subject at creation; "" = unowned/legacy
    intake: dict = Field(default_factory=dict)


class RunAccepted(BaseModel):
    run_id: str
    status: str = "queued"


VisitType = Literal[
    "initial_consultation",
    "follow_up",
    "imaging_review",
    "biopsy_review",
    "staging_review",
    "molecular_review",
    "treatment_planning",
    "post_treatment",
    "surveillance",
    "other",
]


class VisitIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=10_000)

    visit_date: date
    visit_type: VisitType = "follow_up"
    reason: str = Field(default="", max_length=500)
    doctor: str = Field(default="", max_length=128)
    size_mm: float | None = Field(default=None, ge=0, le=500)
    notes: str = Field(default="", max_length=10_000)
    metadata: dict[str, str] = Field(default_factory=dict)


class VisitOut(VisitIn):
    id: str
    case_id: str
    created_at: datetime


FindingOrigin = Literal["ai", "clinician"]
FindingVerification = Literal["pending", "accepted", "rejected", "unknown"]


class FindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=10_000)

    visit_id: str = Field(default="", max_length=64)
    source_doc: str = Field(default="", max_length=512)
    source_kind: str = Field(default="", max_length=64)
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(max_length=2000)
    unit: str = Field(default="", max_length=32)
    origin: FindingOrigin = "ai"
    confidence: Literal["high", "medium", "low"] = "medium"


class FindingOut(FindingIn):
    id: str
    case_id: str
    verification: FindingVerification = "pending"
    verified_by: str = ""
    created_at: datetime
