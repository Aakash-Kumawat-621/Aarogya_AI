import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.core.patient_context import build_patient_context
from app.models.request_models import LocationData, PatientProfile
from app.models.response_models import AnalyzeResponse

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
    Accepts multipart/form-data with optional text, images, and files.
    Returns a structured PatientContext (Stage 1 — RAG + scoring in Module 3).
    """
    start_ms = time.time()
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

    # 3. Validate at least one input is present
    if not symptoms_text and not xray_image and not body_photo and not prescription:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one input: symptoms_text, xray_image, body_photo, or prescription",
        )

    # 4. Read upload bytes
    xray_bytes = await xray_image.read() if xray_image else None
    body_photo_bytes = await body_photo.read() if body_photo else None
    prescription_bytes = await prescription.read() if prescription else None

    # 5. Build patient context (runs all modalities in parallel)
    context = await build_patient_context(
        symptoms_text=symptoms_text,
        patient_profile=patient_profile,
        location=loc_data,
        xray_bytes=xray_bytes,
        body_photo_bytes=body_photo_bytes,
        prescription_bytes=prescription_bytes,
    )

    elapsed_ms = int((time.time() - start_ms) * 1000)

    # 6. Return context-based response
    # NOTE: Full RAG + diagnosis + doctor recommendations wired in Module 3
    return AnalyzeResponse(
        session_id=context.session_id,
        context_built=True,
        inputs_processed=context.inputs_provided,
        symptoms_extracted=len(context.symptom_entities),
        risk_flags=context.risk_flags,
        context_confidence=context.context_confidence,
        primary_concern=context.primary_concern,
        disclaimer="Context built. Full diagnosis will be available once Module 3 (RAG + Bedrock) is wired.",
        processing_time_ms=elapsed_ms,
    )
