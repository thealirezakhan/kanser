from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Modality = Literal["ct", "cxr", "pathology", "genomics", "labs", "notes"]


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=1_000_000)

    patient_ref: str = Field(min_length=1, max_length=128)
    modalities: list[Modality] = Field(default_factory=list)
    clinical_notes: str = Field(default="", max_length=100_000)
    metadata: dict[str, str] = Field(default_factory=dict)


class CaseOut(BaseModel):
    id: str
    patient_ref: str
    modalities: list[str]
    clinical_notes: str
    metadata: dict[str, str]
    created_at: datetime


class RunAccepted(BaseModel):
    run_id: str
    status: str = "queued"
