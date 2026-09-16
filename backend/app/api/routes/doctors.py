"""
backend/app/api/routes/doctors.py

Doctor search endpoints — Module 5.

GET /api/v1/doctors/search  — Find specialists near patient's location
GET /api/v1/doctors/specialties — List all supported specialties
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.response_models import DoctorResult
from app.modules.doctors.finder import find_doctors
from app.modules.doctors.specialty_mapper import get_specialty_result, _CONDITION_MAP

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Doctors"])
limiter = Limiter(key_func=get_remote_address)


class DoctorSearchResponse(BaseModel):
    condition: str
    specialty: str
    doctors: List[DoctorResult]
    total_found: int
    source: str                   # "google_places" | "nmc_registry" | "fallback"
    location_used: bool


@router.get("/doctors/search", response_model=DoctorSearchResponse)
@limiter.limit("30/minute")
async def search_doctors(
    request: Request,
    condition: str = Query(..., description="Medical condition or symptom"),
    lat: Optional[float] = Query(None, ge=-90, le=90, description="Patient latitude"),
    lng: Optional[float] = Query(None, ge=-180, le=180, description="Patient longitude"),
    gender: Optional[str] = Query(None, description="Patient gender for specialty overrides"),
    age: Optional[int] = Query(None, ge=0, le=120, description="Patient age for pediatric/geriatric routing"),
    urgency: str = Query("low", description="Urgency level: low|moderate|urgent|emergency"),
    top_k: int = Query(5, ge=1, le=10),
):
    """
    Find nearby doctors for a given condition.

    - Applies gender/age overrides (e.g. UTI in female → Gynecologist)
    - Emergency cases search nearest hospitals within 5km
    - Results from Google Places (if location provided), else static fallback
    """
    # Map condition to specialty
    specialty_result = get_specialty_result(
        condition=condition,
        gender=gender,
        age=age,
        urgency=urgency,
    )

    doctors = await find_doctors(
        condition=condition,
        specialty=specialty_result.primary,
        google_search_term=specialty_result.google_search_term,
        lat=lat,
        lng=lng,
        urgency=urgency,
        emergency_dept=specialty_result.emergency_dept,
        top_k=top_k,
    )

    source = doctors[0].source if doctors else "fallback"
    return DoctorSearchResponse(
        condition=condition,
        specialty=specialty_result.primary,
        doctors=doctors,
        total_found=len(doctors),
        source=source,
        location_used=lat is not None and lng is not None,
    )


@router.get("/doctors/specialties")
async def list_specialties():
    """Return all supported condition → specialist mappings."""
    from app.modules.doctors.specialty_mapper import _CONDITION_MAP
    specialties = sorted(set(v[0] for v in _CONDITION_MAP.values()))
    conditions_by_specialty: dict[str, list] = {}
    for condition, (spec, _, _) in _CONDITION_MAP.items():
        conditions_by_specialty.setdefault(spec, []).append(condition)
    return {
        "total_conditions": len(_CONDITION_MAP),
        "total_specialties": len(specialties),
        "specialties": sorted(specialties),
        "conditions_by_specialty": {k: sorted(v) for k, v in sorted(conditions_by_specialty.items())},
    }
