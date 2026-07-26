from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

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
    session_id: str
    diagnosis: Diagnosis
    urgency: Urgency
    recommendations: List[DoctorResult] = []
    disclaimer: str
    processing_time_ms: int
