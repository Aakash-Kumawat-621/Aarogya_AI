import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.patient_context import build_patient_context
from app.core.response_builder import build_response
from app.models.request_models import LocationData, PatientProfile
from app.models.response_models import AnalyzeResponse
from app.modules.doctors import finder, specialty_mapper
from app.modules.rag import chain
from app.services.dynamodb_service import save_session
from app.utils.metrics import emit_metric

router = APIRouter(tags=["Analyze"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)


@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit("10/minute")
async def analyze_symptoms(
    request: Request,
    symptoms_text: Optional[str] = Form(None),
    patient: str = Form(...),
    location: Optional[str] = Form(None),
    xray_image: Optional[UploadFile] = File(None),
    body_photo: Optional[UploadFile] = File(None),
    prescription: Optional[UploadFile] = File(None),
):
    """
    Primary endpoint for medical analysis.

    Full Module 4 pipeline:
      1. Build PatientContext from all 5 modalities (parallel)
      2. Run XGBoost (symptom → disease) + ResNet-50 (X-ray) concurrently
      3. Feed ML outputs into LightGBM severity scorer
      4. RAG chain enriched with ML predictions → DiagnosisResult
      5. Map specialty → find doctors
      6. Assemble and return AnalyzeResponse
      7. Persist session to DynamoDB (fire-and-forget)
    """
    start_ms = time.time()
    logger.info("Received /analyze request")

    # ── 1. Parse patient JSON ──────────────────────────────────────────────
    try:
        patient_dict = json.loads(patient)
        patient_profile = PatientProfile(**patient_dict)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for 'patient'")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # ── 2. Parse location JSON ─────────────────────────────────────────────
    loc_data = None
    if location:
        try:
            loc_dict = json.loads(location)
            loc_data = LocationData(**loc_dict)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON for 'location'")
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

    # ── 3. Validate at least one input is present ──────────────────────────
    if not symptoms_text and not xray_image and not body_photo and not prescription:
        raise HTTPException(
            status_code=400,
            detail="Must provide at least one input: symptoms_text, xray_image, body_photo, or prescription",
        )

    # ── 3b. Sanitize and cap symptoms_text ────────────────────────────────
    if symptoms_text:
        import re
        # Strip HTML tags
        symptoms_text = re.sub(r"<[^>]+>", " ", symptoms_text)
        # Remove control characters (except newlines/tabs)
        symptoms_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", symptoms_text)
        # Normalize whitespace
        symptoms_text = " ".join(symptoms_text.split())
        # Cap at 2000 characters to prevent OOM / Bedrock token overflow
        if len(symptoms_text) > 2000:
            logger.warning(
                f"symptoms_text truncated from {len(symptoms_text)} to 2000 characters"
            )
            symptoms_text = symptoms_text[:2000]

    # ── 4. Read upload bytes ───────────────────────────────────────────────
    xray_bytes = await xray_image.read() if xray_image else None
    body_photo_bytes = await body_photo.read() if body_photo else None
    prescription_bytes = await prescription.read() if prescription else None

    # ── 5. Build PatientContext (all modalities in parallel) ───────────────
    context = await build_patient_context(
        symptoms_text=symptoms_text,
        patient_profile=patient_profile,
        location=loc_data,
        xray_bytes=xray_bytes,
        body_photo_bytes=body_photo_bytes,
        prescription_bytes=prescription_bytes,
    )

    # ── 6. ML inference — XGBoost + X-ray classifier concurrently ─────────
    xgb_predictions = []
    xray_result_ml = None

    try:
        from app.modules.ml.symptom_classifier import classify_symptoms
        from app.modules.image.xray_classifier import classify_xray

        # Run XGBoost and ResNet-50 concurrently (both CPU-bound, thread pool)
        xgb_task = asyncio.to_thread(classify_symptoms, context)

        if xray_bytes:
            xray_task = asyncio.to_thread(classify_xray, xray_bytes)
            xgb_predictions, xray_result_ml = await asyncio.gather(
                xgb_task, xray_task, return_exceptions=True
            )
        else:
            xgb_predictions = await xgb_task

        # Handle exceptions from gather (non-fatal)
        if isinstance(xgb_predictions, Exception):
            logger.warning(f"XGBoost inference failed (non-fatal): {xgb_predictions}")
            xgb_predictions = []
        if isinstance(xray_result_ml, Exception):
            logger.warning(f"X-ray classifier failed (non-fatal): {xray_result_ml}")
            xray_result_ml = None

        # Store X-ray ML results in context for downstream use
        if xray_result_ml and xray_result_ml.get("ml_backed"):
            context.body_photo_findings = context.body_photo_findings or {}
            context.body_photo_findings["xray_ml"] = xray_result_ml

        logger.info(
            f"ML inference: XGBoost top={xgb_predictions[0]['disease'] if xgb_predictions else 'N/A'}, "
            f"X-ray={xray_result_ml.get('top_condition') if xray_result_ml else 'N/A'}"
        )

    except Exception as e:
        logger.warning(f"ML inference layer failed (non-fatal): {e}")
        xgb_predictions = []
        xray_result_ml = None

    # ── 7. LightGBM severity scorer ────────────────────────────────────────
    urgency_result = None
    try:
        from app.modules.ml.severity_scorer import score_urgency
        urgency_result = await asyncio.to_thread(score_urgency, context, xgb_predictions)
        logger.info(f"Urgency: {urgency_result['level'].upper()} (ml_backed={urgency_result.get('ml_backed')})")
    except Exception as e:
        logger.warning(f"Severity scorer failed (non-fatal): {e}")
        urgency_result = None

    # ── 8. RAG chain — enriched with ML context ───────────────────────────
    try:
        # Pass ML predictions into chain context
        diagnosis = chain.run(context, ml_predictions={
            "xgb_top_disease": xgb_predictions[0]["disease"] if xgb_predictions else None,
            "xgb_top_prob": xgb_predictions[0]["probability"] if xgb_predictions else None,
            "xgb_top3": xgb_predictions[:3] if xgb_predictions else [],
            "urgency_level": urgency_result["level"] if urgency_result else None,
            "xray_top_condition": xray_result_ml.get("top_condition") if xray_result_ml else None,
        })
    except Exception as e:
        logger.error(f"RAG chain failed: {e}")
        elapsed = int((time.time() - start_ms) * 1000)
        # Graceful degradation: return ML results even if RAG fails
        return _build_degraded_response(
            context=context,
            xgb_predictions=xgb_predictions,
            urgency_result=urgency_result,
            elapsed_ms=elapsed,
        )

    # ── 9. Doctor finder ───────────────────────────────────────────────────
    # Prefer ML-predicted specialist over RAG specialist ONLY IF confidence is decent
    # Otherwise, an empty feature vector defaults to "Urinary tract infection"
    primary_disease = None
    if xgb_predictions and xgb_predictions[0].get("disease") and xgb_predictions[0].get("probability", 0) > 0.25:
        primary_disease = xgb_predictions[0]["disease"]
    specialist = None
    if primary_disease:
        spec_result = specialty_mapper.get_specialty_result(primary_disease)
        specialist = spec_result.primary
    if not specialist:
        spec_result = specialty_mapper.get_specialty_result(context.primary_concern or "general")
        specialist = spec_result.primary
    if not specialist and diagnosis:
        specialist = getattr(diagnosis, "specialist_needed", None) or "General Physician"

    # Get patient location from context if available
    loc = getattr(context, "location", None)
    p_lat = getattr(loc, "latitude", None) if loc else None
    p_lng = getattr(loc, "longitude", None) if loc else None

    doctors = await finder.find_doctors(
        condition=primary_disease or context.primary_concern or "general",
        specialty=specialist,
        google_search_term=f"{specialist} doctor near me",
        lat=p_lat,
        lng=p_lng,
        urgency=urgency_result.get("level", "low") if urgency_result else "low",
        emergency_dept=(urgency_result.get("call_emergency", False) if urgency_result else False),
        top_k=3,
    )

    # ── 10. Assemble final response ────────────────────────────────────────
    elapsed_ms = int((time.time() - start_ms) * 1000)
    response = build_response(
        context=context,
        diagnosis=diagnosis,
        doctors=doctors,
        processing_time_ms=elapsed_ms,
        urgency_override=urgency_result,  # ML urgency takes precedence
        xgb_top_disease=primary_disease,  # Override context.primary_concern with real disease
    )

    # ── 11. CloudWatch metrics (fire-and-forget) ──────────────────────────
    urgency_level = urgency_result.get("level", "unknown") if urgency_result else "unknown"
    modalities_used = sum([
        1 if symptoms_text else 0,
        1 if xray_image else 0,
        1 if body_photo else 0,
        1 if prescription else 0,
    ])
    await emit_metric("AnalyzeLatency", elapsed_ms, "Milliseconds")
    await emit_metric("UrgencyDistribution", 1, "Count", {"UrgencyLevel": urgency_level.upper()})
    await emit_metric("InputModalities", modalities_used, "Count")

    # ── 12. Persist session (fire-and-forget) ─────────────────────────────
    try:
        context_dict = context.model_dump()
        diagnosis_dict = {
            "condition_name": diagnosis.condition_name,
            "confidence": diagnosis.confidence,
            "severity_level": diagnosis.severity_level,
            "specialist_needed": diagnosis.specialist_needed,
            "citations": diagnosis.citations,
            "requires_emergency_attention": getattr(diagnosis, "requires_emergency_attention", False),
            "ml_backed_disease": xgb_predictions[0]["disease"] if xgb_predictions else None,
            "ml_urgency": urgency_result["level"] if urgency_result else None,
        }
        save_session(context.session_id, context_dict, diagnosis_dict)
    except Exception as e:
        logger.warning(f"Session persistence failed (non-fatal): {e}")

    return response


def _build_degraded_response(
    context,
    xgb_predictions: list,
    urgency_result: Optional[dict],
    elapsed_ms: int,
) -> AnalyzeResponse:
    """
    Graceful degradation response when RAG chain fails.
    Returns ML-backed urgency + top disease even without full diagnosis.
    """
    from app.models.response_models import Urgency, SeverityLevel

    urgency = None
    if urgency_result:
        level_map = {
            "low": SeverityLevel.low,
            "moderate": SeverityLevel.moderate,
            "urgent": SeverityLevel.urgent,
            "emergency": SeverityLevel.emergency,
        }
        urgency = Urgency(
            level=level_map.get(urgency_result["level"], SeverityLevel.low),
            action_plan=urgency_result.get("action_plan", ["Please consult a doctor"]),
            call_emergency=urgency_result.get("call_emergency", False),
        )

    top_disease = xgb_predictions[0]["disease"] if xgb_predictions else None
    disclaimer_prefix = "EMERGENCY: Call 112 immediately! " if (urgency_result and urgency_result.get("call_emergency")) else ""

    return AnalyzeResponse(
        session_id=context.session_id,
        context_built=True,
        inputs_processed=context.inputs_provided,
        symptoms_extracted=len(context.symptom_entities),
        risk_flags=context.risk_flags,
        context_confidence=round(context.context_confidence, 3),
        primary_concern=top_disease or context.primary_concern,
        urgency=urgency,
        disclaimer=(
            f"{disclaimer_prefix}AI diagnosis assistance provided. "
            "Always consult a qualified doctor. This is NOT a substitute for medical advice."
        ),
        processing_time_ms=elapsed_ms,
    )
