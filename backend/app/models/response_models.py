from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    low = "low"
    moderate = "moderate"
    urgent = "urgent"
    emergency = "emergency"


class Diagnosis(BaseModel):
    condition_name: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    severity_level: SeverityLevel
    specialist_needed: str
    citations: List[str] = []


class Urgency(BaseModel):
    level: SeverityLevel
    action_plan: List[str]
    call_emergency: bool


class DoctorResult(BaseModel):
    name: str
    specialty: str
    hospital: str
    rating: float = Field(..., ge=0.0, le=5.0)
    distance_km: float
    phone: str
    address: str


class AnalyzeResponse(BaseModel):
    """
    Response from POST /analyze.
    In Module 2: returns PatientContext summary.
    In Module 3+: will include full diagnosis, urgency, and doctor recommendations.
    """

    session_id: str

    # Module 2 context fields
    context_built: bool = False
    inputs_processed: List[str] = []
    symptoms_extracted: int = 0
    risk_flags: List[str] = []
    context_confidence: float = 0.0
    primary_concern: Optional[str] = None

    # Module 3+ fields (optional until wired)
    diagnosis: Optional[Diagnosis] = None
    urgency: Optional[Urgency] = None
    recommendations: List[DoctorResult] = []

    disclaimer: str
    processing_time_ms: int
