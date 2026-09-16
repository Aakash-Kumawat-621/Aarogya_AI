"""
backend/app/api/routes/conversation.py

Multi-turn diagnostic conversation endpoints.

POST /api/v1/session/start   — Start a new diagnostic session
POST /api/v1/session/respond — Submit answers + self-exam results for a turn
GET  /api/v1/session/{id}    — Retrieve session state
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.core.patient_context import build_patient_context
from app.models.request_models import PatientProfile
from app.models.response_models import AnalyzeResponse
from app.modules.conversation import (
    confidence_evaluator,
    question_generator,
    self_exam_guide,
    session_manager,
)
from app.modules.doctors import finder, specialty_mapper
from app.modules.rag import chain
from app.services.dynamodb_service import save_session

router = APIRouter(prefix="/session", tags=["Conversation"])
logger = logging.getLogger(__name__)

MAX_SYMPTOMS_LEN = 2000

# ── Pydantic response models ───────────────────────────────────────────────────

class FollowUpQuestion(BaseModel):
    id: str
    text: str
    type: str                       # "yes_no" | "multiple_choice"
    options: Optional[list[str]] = None


class SelfExamInstruction(BaseModel):
    id: str
    title: str
    why_useful: str
    steps: list[str]
    input_type: str                  # "number" | "choice" | "text"
    unit: Optional[str] = None
    choices: Optional[list[str]] = None
    normal_range: Optional[str] = None


class ConversationResponse(BaseModel):
    session_id: str
    status: str                      # "needs_followup" | "complete"
    turn: int
    # Populated when status == "needs_followup"
    initial_analysis: Optional[str] = None
    questions: list[FollowUpQuestion] = []
    self_exams: list[SelfExamInstruction] = []
    # Populated when status == "complete"
    diagnosis: Optional[dict] = None
    urgency: Optional[dict] = None
    doctors: list[dict] = []
    disclaimer: str = (
        "⚠️ This is an AI-assisted health information tool. "
        "It is NOT a substitute for professional medical advice, diagnosis, or treatment. "
        "Always consult a qualified healthcare provider."
    )
    processing_time_ms: int = 0


# ── Helper: run the full diagnosis pipeline ───────────────────────────────────

async def _run_full_diagnosis(
    context,
    xgb_predictions: list[dict],
    urgency_result: Optional[dict],
    session_id: str,
    start_ms: float,
    confidence_note: Optional[str] = None,
) -> dict:
    """
    Run RAG chain + doctor finder + response assembly.
    Returns a dict suitable for ConversationResponse.
    """
    from app.core.response_builder import build_response

    try:
        diagnosis = chain.run(context, ml_predictions={
            "xgb_top_disease": xgb_predictions[0]["disease"] if xgb_predictions else None,
            "xgb_top_prob": xgb_predictions[0]["probability"] if xgb_predictions else None,
            "xgb_top3": xgb_predictions[:3] if xgb_predictions else [],
            "urgency_level": urgency_result["level"] if urgency_result else None,
            "xray_top_condition": None,
        })
    except Exception as e:
        logger.error(f"RAG chain failed in conversation: {e}")
        diagnosis = None

    # Doctor finder
    specialist = None
    if xgb_predictions:
        specialist = specialty_mapper.map_to_specialty(xgb_predictions[0].get("disease", ""))
    if not specialist and diagnosis:
        specialist = getattr(diagnosis, "specialist_needed", None)
    doctors = finder.find_doctors(specialist, top_k=3)

    # Build structured response
    elapsed_ms = int((time.time() - start_ms) * 1000)

    disclaimer = (
        "⚠️ This is an AI-assisted health information tool. "
        "It is NOT a substitute for professional medical advice, diagnosis, or treatment. "
        "Always consult a qualified healthcare provider."
    )
    if confidence_note:
        disclaimer = f"{confidence_note}\n\n{disclaimer}"

    diagnosis_dict = None
    urgency_dict = None

    if diagnosis:
        diagnosis_dict = {
            "condition_name": diagnosis.condition_name,
            "confidence": diagnosis.confidence,
            "explanation": diagnosis.explanation,
            "severity_level": diagnosis.severity_level,
            "specialist_needed": diagnosis.specialist_needed,
            "citations": diagnosis.citations,
            "requires_emergency_attention": diagnosis.requires_emergency_attention,
        }
    
    if urgency_result:
        urgency_dict = {
            "level": urgency_result["level"],
            "score": urgency_result.get("score", 0.5),
            "call_emergency": urgency_result.get("call_emergency", False),
            "action_plan": urgency_result.get("action_plan", []),
            "ml_backed": urgency_result.get("ml_backed", False),
        }

    doctors_list = []
    for d in (doctors or []):
        if isinstance(d, dict):
            doctors_list.append(d)
        else:
            doctors_list.append(d.dict() if hasattr(d, "dict") else {})

    # Persist session
    try:
        if diagnosis:
            session_manager.complete_session(session_id, diagnosis_dict)
    except Exception as e:
        logger.warning(f"Session completion persist failed: {e}")

    return {
        "diagnosis": diagnosis_dict,
        "urgency": urgency_dict,
        "doctors": doctors_list,
        "disclaimer": disclaimer,
        "processing_time_ms": elapsed_ms,
    }


# ── POST /session/start ────────────────────────────────────────────────────────

@router.post("/start", response_model=ConversationResponse)
async def start_session(
    symptoms_text: str = Form(...),
    patient: str = Form(...),
    xray_image: Optional[UploadFile] = File(None),
    body_photo: Optional[UploadFile] = File(None),
    prescription: Optional[UploadFile] = File(None),
    lab_report: Optional[UploadFile] = File(None),
):
    """
    Start a new multi-turn diagnostic session.

    1. Parse patient + symptoms
    2. Run XGBoost to get initial differential diagnoses
    3. Check confidence → either diagnose immediately or ask follow-up questions
    """
    start_ms = time.time()
    session_id = str(uuid.uuid4())

    # ── Parse patient profile ─────────────────────────────────────────────
    try:
        from pydantic import ValidationError
        patient_dict = json.loads(patient)
        patient_profile = PatientProfile(**patient_dict)
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(status_code=400, detail=f"Invalid patient data: {e}")

    # ── Sanitize symptoms ─────────────────────────────────────────────────
    import re
    symptoms_text = re.sub(r"<[^>]+>", " ", symptoms_text)
    symptoms_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", symptoms_text)
    symptoms_text = " ".join(symptoms_text.split())
    if len(symptoms_text) > MAX_SYMPTOMS_LEN:
        symptoms_text = symptoms_text[:MAX_SYMPTOMS_LEN]

    if not symptoms_text.strip():
        raise HTTPException(status_code=400, detail="symptoms_text is required")

    # ── Read optional uploaded files ──────────────────────────────────────
    xray_bytes = await xray_image.read() if xray_image else None
    body_photo_bytes = await body_photo.read() if body_photo else None
    # Merge prescription + lab report into prescription channel (both are documents)
    prescription_bytes = None
    if prescription:
        prescription_bytes = await prescription.read()
    elif lab_report:
        prescription_bytes = await lab_report.read()

    # ── Build patient context ─────────────────────────────────────────────
    context = await build_patient_context(
        symptoms_text=symptoms_text,
        patient_profile=patient_profile,
        location=None,
        xray_bytes=xray_bytes,
        body_photo_bytes=body_photo_bytes,
        prescription_bytes=prescription_bytes,
    )
    context.session_id = session_id

    # ── Run XGBoost ───────────────────────────────────────────────────────
    xgb_predictions = []
    try:
        from app.modules.ml.symptom_classifier import classify_symptoms
        xgb_predictions = await asyncio.to_thread(classify_symptoms, context)
    except Exception as e:
        logger.warning(f"XGBoost failed in conversation start: {e}")

    # ── Run urgency scorer ────────────────────────────────────────────────
    urgency_result = None
    try:
        from app.modules.ml.severity_scorer import score_urgency
        urgency_result = await asyncio.to_thread(score_urgency, context, xgb_predictions)
    except Exception as e:
        logger.warning(f"Severity scorer failed: {e}")

    # ── Check emergency bypass ────────────────────────────────────────────
    emergency_bypass = confidence_evaluator.check_emergency_bypass(context)
    if urgency_result and urgency_result.get("level") == "emergency":
        emergency_bypass = True

    if emergency_bypass:
        logger.warning(f"Emergency bypass — skipping follow-up for session {session_id}")
        result = await _run_full_diagnosis(
            context, xgb_predictions, urgency_result, session_id, start_ms
        )
        return ConversationResponse(
            session_id=session_id,
            status="complete",
            turn=0,
            **result,
        )

    # ── Decide: diagnose now or ask questions ─────────────────────────────
    should_dx, reason = confidence_evaluator.should_diagnose(
        xgb_predictions, turn=0, context=context, urgency_result=urgency_result
    )

    if should_dx:
        result = await _run_full_diagnosis(
            context, xgb_predictions, urgency_result, session_id, start_ms
        )
        return ConversationResponse(
            session_id=session_id,
            status="complete",
            turn=0,
            **result,
        )

    # ── Generate follow-up questions ──────────────────────────────────────
    available_exam_ids = list(self_exam_guide.SELF_EXAM_LIBRARY.keys())
    top_diseases = [p.get("disease", "") for p in xgb_predictions[:3]]
    top_disease_str = " / ".join(top_diseases[:3]) if top_diseases else "your symptoms"

    question_data = await asyncio.to_thread(
        question_generator.generate_followup_questions,
        context,
        xgb_predictions,
        turn=1,
        available_exam_ids=available_exam_ids,
    )

    # Emergency detected by question generator
    if question_data.get("emergency_flag"):
        result = await _run_full_diagnosis(
            context, xgb_predictions, urgency_result, session_id, start_ms
        )
        return ConversationResponse(
            session_id=session_id,
            status="complete",
            turn=0,
            **result,
        )

    # ── Persist session ───────────────────────────────────────────────────
    session_manager.create_session(
        session_id=session_id,
        patient_profile=patient_dict,
        initial_symptoms_text=symptoms_text,
        differential_diagnoses=xgb_predictions[:3],
    )

    # ── Build response ────────────────────────────────────────────────────
    questions = [
        FollowUpQuestion(**q) for q in question_data.get("questions", [])
    ]
    self_exams = [
        SelfExamInstruction(**e) for e in question_data.get("recommended_self_exams", [])
    ]

    top_prob = xgb_predictions[0]["probability"] if xgb_predictions else 0.0
    initial_analysis = (
        f"Your symptoms could suggest {len(top_diseases)} possible conditions: "
        f"{', '.join(top_diseases[:3])}. "
        f"To help narrow this down, I have a few questions and a quick self-check for you."
    )

    elapsed_ms = int((time.time() - start_ms) * 1000)
    return ConversationResponse(
        session_id=session_id,
        status="needs_followup",
        turn=1,
        initial_analysis=initial_analysis,
        questions=questions,
        self_exams=self_exams,
        processing_time_ms=elapsed_ms,
    )


# ── POST /session/respond ──────────────────────────────────────────────────────

@router.post("/respond", response_model=ConversationResponse)
async def respond_to_session(
    session_id: str = Form(...),
    answers: str = Form(...),         # JSON dict: {"q1": "Dull/pressure", "q2": "yes"}
    self_exam_results: str = Form(default="{}"),  # JSON dict: {"pulse_rate": 108}
):
    """
    Submit answers + self-exam results for a conversation turn.

    1. Load session from DynamoDB
    2. Merge answers into enriched symptom text
    3. Re-run XGBoost with enriched context
    4. Check confidence again → diagnose or ask another round
    """
    start_ms = time.time()

    # ── Load session ──────────────────────────────────────────────────────
    session = session_manager.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    if session.get("status") == "complete":
        raise HTTPException(status_code=400, detail="Session is already complete")

    # ── Parse answers ─────────────────────────────────────────────────────
    try:
        answers_dict = json.loads(answers)
        self_exam_dict = json.loads(self_exam_results)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in answers or self_exam_results: {e}")

    # ── Rebuild enriched patient context ──────────────────────────────────
    patient_profile_dict = session.get("patient_profile", {})
    try:
        from pydantic import ValidationError
        patient_profile = PatientProfile(**patient_profile_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session patient profile corrupted: {e}")

    # Merge all accumulated data into enriched symptoms text
    # First save this turn's data to get the full accumulated picture
    prev_differential = session.get("differential_diagnoses", [])
    session = session_manager.append_turn(
        session_id=session_id,
        questions_asked=[],  # We don't store questions asked (already in previous turn)
        self_exams_asked=[],
        answers=answers_dict,
        self_exam_results=self_exam_dict,
        differential_diagnoses=prev_differential,
    )
    if not session:
        raise HTTPException(status_code=500, detail="Failed to update session")

    enriched_symptoms = session_manager.build_enriched_symptoms_text(session)
    current_turn = session["turn"]

    # ── Rebuild patient context with enriched symptoms ─────────────────────
    context = await build_patient_context(
        symptoms_text=enriched_symptoms,
        patient_profile=patient_profile,
        location=None,
        xray_bytes=None,
        body_photo_bytes=None,
        prescription_bytes=None,
    )
    context.session_id = session_id

    # ── Re-run XGBoost with enriched context ─────────────────────────────
    xgb_predictions = []
    try:
        from app.modules.ml.symptom_classifier import classify_symptoms
        xgb_predictions = await asyncio.to_thread(classify_symptoms, context)
    except Exception as e:
        logger.warning(f"XGBoost failed in conversation respond: {e}")
        # Fall back to previous differential
        xgb_predictions = session.get("differential_diagnoses", [])

    # Update the session's differential in-memory (no new turn increment)
    if xgb_predictions:
        from app.modules.conversation import session_manager as sm
        cached = sm._memory_store.get(session_id)
        if cached:
            cached["differential_diagnoses"] = xgb_predictions[:3]
            cached["current_top_prob"] = xgb_predictions[0].get("probability", 0.0)
        session["differential_diagnoses"] = xgb_predictions[:3]
        session["current_top_prob"] = xgb_predictions[0].get("probability", 0.0)

    # ── Run urgency scorer ────────────────────────────────────────────────
    urgency_result = None
    try:
        from app.modules.ml.severity_scorer import score_urgency
        urgency_result = await asyncio.to_thread(score_urgency, context, xgb_predictions)
    except Exception as e:
        logger.warning(f"Severity scorer failed: {e}")

    # ── Check emergency bypass ────────────────────────────────────────────
    emergency_bypass = confidence_evaluator.check_emergency_bypass(context)
    if urgency_result and urgency_result.get("level") == "emergency":
        emergency_bypass = True

    if emergency_bypass:
        result = await _run_full_diagnosis(
            context, xgb_predictions, urgency_result, session_id, start_ms
        )
        return ConversationResponse(
            session_id=session_id,
            status="complete",
            turn=current_turn,
            **result,
        )

    # ── Decide: diagnose now or ask another round ─────────────────────────
    should_dx, reason = confidence_evaluator.should_diagnose(
        xgb_predictions, turn=current_turn, context=context, urgency_result=urgency_result
    )
    confidence_note = confidence_evaluator.get_confidence_note(reason, current_turn)

    if should_dx:
        result = await _run_full_diagnosis(
            context, xgb_predictions, urgency_result, session_id, start_ms,
            confidence_note=confidence_note,
        )
        return ConversationResponse(
            session_id=session_id,
            status="complete",
            turn=current_turn,
            **result,
        )

    # ── Generate another round of follow-up questions ─────────────────────
    available_exam_ids = list(self_exam_guide.SELF_EXAM_LIBRARY.keys())
    question_data = await asyncio.to_thread(
        question_generator.generate_followup_questions,
        context,
        xgb_predictions,
        turn=current_turn + 1,
        available_exam_ids=available_exam_ids,
    )

    if question_data.get("emergency_flag"):
        result = await _run_full_diagnosis(
            context, xgb_predictions, urgency_result, session_id, start_ms
        )
        return ConversationResponse(
            session_id=session_id,
            status="complete",
            turn=current_turn,
            **result,
        )

    questions = [FollowUpQuestion(**q) for q in question_data.get("questions", [])]
    self_exams = [SelfExamInstruction(**e) for e in question_data.get("recommended_self_exams", [])]

    elapsed_ms = int((time.time() - start_ms) * 1000)
    return ConversationResponse(
        session_id=session_id,
        status="needs_followup",
        turn=current_turn + 1,
        initial_analysis=question_data.get("reasoning", ""),
        questions=questions,
        self_exams=self_exams,
        processing_time_ms=elapsed_ms,
    )


# ── GET /session/{session_id} ──────────────────────────────────────────────────

@router.get("/{session_id}")
async def get_session(session_id: str):
    """Retrieve current session state."""
    session = session_manager.load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    # Remove internal fields before returning
    session.pop("expires_at", None)
    return session
