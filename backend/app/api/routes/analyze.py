import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.core.patient_context import build_patient_context
from app.core.response_builder import build_response
from app.models.request_models import LocationData, PatientProfile
from app.models.response_models import AnalyzeResponse
from app.modules.doctors import finder, specialty_mapper
from app.modules.rag import chain
from app.services.dynamodb_service import save_session

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

    Accepts multipart/form-data. Runs the full pipeline:
      1. Build PatientContext from all 5 modalities (parallel)
      2. RAG chain: query → retrieve → Bedrock → DiagnosisResult
      3. Map specialty → find doctors
      4. Assemble and return AnalyzeResponse
      5. Persist session to DynamoDB (non-blocking)
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

    # 5. Build patient context (all modalities in parallel)
    context = await build_patient_context(
        symptoms_text=symptoms_text,
        patient_profile=patient_profile,
        location=loc_data,
        xray_bytes=xray_bytes,
        body_photo_bytes=body_photo_bytes,
        prescription_bytes=prescription_bytes,
    )

    # 6. RAG chain → DiagnosisResult
    try:
        diagnosis = chain.run(context)
    except Exception as e:
        logger.error(f"RAG chain failed: {e}")
        # Graceful degradation: return context summary without diagnosis
        elapsed = int((time.time() - start_ms) * 1000)
        return AnalyzeResponse(
            session_id=context.session_id,
            context_built=True,
            inputs_processed=context.inputs_provided,
            symptoms_extracted=len(context.symptom_entities),
            risk_flags=context.risk_flags,
            context_confidence=round(context.context_confidence, 3),
            primary_concern=context.primary_concern,
            disclaimer=(
                "⚠️ AI diagnosis temporarily unavailable. "
                "Please consult a doctor. This is NOT a medical diagnosis."
            ),
            processing_time_ms=elapsed,
        )

    # 7. Map specialty → find doctors
    specialty = specialty_mapper.map_to_specialty(context.primary_concern)
    doctors = finder.find_doctors(specialty, top_k=3)

    # 8. Assemble final response
    elapsed_ms = int((time.time() - start_ms) * 1000)
    response = build_response(context, diagnosis, doctors, elapsed_ms)

    # 9. Persist session (fire-and-forget — non-fatal on failure)
    try:
        context_dict = context.model_dump()
        diagnosis_dict = {
            "condition_name": diagnosis.condition_name,
            "confidence": diagnosis.confidence,
            "severity_level": diagnosis.severity_level,
            "specialist_needed": diagnosis.specialist_needed,
            "citations": diagnosis.citations,
            "requires_emergency_attention": diagnosis.requires_emergency_attention,
        }
        save_session(context.session_id, context_dict, diagnosis_dict)
    except Exception as e:
        logger.warning(f"Session persistence failed (non-fatal): {e}")

    return response
