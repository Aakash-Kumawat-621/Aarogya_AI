import json
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.models.request_models import LocationData, PatientProfile
from app.models.response_models import (
    AnalyzeResponse,
    Diagnosis,
    DoctorResult,
    SeverityLevel,
    Urgency,
)

router = APIRouter(tags=["Analyze"])
logger = logging.getLogger(__name__)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_symptoms(
    symptoms_text: Optional[str] = Form(None),
    patient: str = Form(...),
    location: Optional[str] = Form(None),
    xray_image: Optional[UploadFile] = File(None),
    body_photo: Optional[UploadFile] = File(None),
    prescription: Optional[UploadFile] = File(None),
):
    """
    Primary endpoint for medical analysis.
    Accepts multipart/form-data.
    """
    logger.info("Received /analyze request")

    # 1. Parse patient JSON
    try:
        patient_dict = json.loads(patient)
        patient_profile = PatientProfile(**patient_dict)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for 'patient'")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # 2. Parse location JSON
    loc_data = None
    if location:
        try:
            loc_dict = json.loads(location)
            loc_data = LocationData(**loc_dict)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON for 'location'")
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    # 3. Validate at least one input exists
    if not symptoms_text and not xray_image and not body_photo and not prescription:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one input: symptoms_text, xray_image, body_photo, or prescription",
        )

    # 4. Return STUB RESPONSE (Will be replaced with actual pipeline later)
    return AnalyzeResponse(
        session_id="test-1234-uuid",
        diagnosis=Diagnosis(
            condition_name="Migraine (Stub Data)",
            confidence=0.85,
            explanation="Based on the reported headache and fever. (This is a placeholder response).",
            severity_level=SeverityLevel.moderate,
            specialist_needed="Neurologist",
            citations=["https://medlineplus.gov/ency/article/000709.htm"],
        ),
        urgency=Urgency(
            level=SeverityLevel.moderate,
            action_plan=[
                "Rest in a dark room",
                "Take over the counter pain medication",
            ],
            call_emergency=False,
        ),
        recommendations=[
            DoctorResult(
                name="Dr. Smith",
                specialty="Neurologist",
                hospital="City General",
                rating=4.5,
                distance_km=2.5,
                phone="+1234567890",
                address="123 Main St",
            )
        ],
        disclaimer="This is an AI generated stub response and not real medical advice.",
        processing_time_ms=120,
    )
