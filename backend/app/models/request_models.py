from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class SmokingStatus(str, Enum):
    never = "never"
    former = "former"
    current = "current"

class ActivityLevel(str, Enum):
    sedentary = "sedentary"
    light = "light"
    moderate = "moderate"
    active = "active"

class PatientProfile(BaseModel):
    # Demographics — required
    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(..., ge=0, le=120)
    gender: str = Field(..., pattern="^(male|female|other)$")

    # Body metrics — optional
    height_cm: Optional[float] = Field(None, ge=50, le=250)
    weight_kg: Optional[float] = Field(None, ge=2, le=300)
    blood_group: Optional[str] = None

    # Medical history — optional lists
    conditions: Optional[List[str]] = []
    allergies: Optional[List[str]] = []
    medications: Optional[List[str]] = []

    # Lifestyle — optional enums
    smoking: SmokingStatus = SmokingStatus.never
    pack_years: Optional[float] = None  # only if smoking==current/former
    alcohol_units_per_week: Optional[int] = Field(None, ge=0, le=200)
    activity_level: ActivityLevel = ActivityLevel.moderate
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)

    # Family history
    family_history: Optional[List[str]] = []

class LocationData(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    city: Optional[str] = None

# AnalyzeRequest — at least one input required
class AnalyzeRequest(BaseModel):
    symptoms_text: Optional[str] = Field(None, max_length=2000)
    patient: PatientProfile
    location: Optional[LocationData] = None
    # xray_image, body_photo, prescription — come as multipart files
    # handled separately in FastAPI route, not in Pydantic model
