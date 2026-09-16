"""
backend/app/core/response_builder.py

Assembles the final AnalyzeResponse from all module outputs:
  PatientContext + DiagnosisResult + DoctorResult list → AnalyzeResponse
"""

import logging
import time

from app.core.patient_context import PatientContext
from app.models.response_models import (
    AnalyzeResponse,
    Diagnosis,
    DoctorResult,
    SeverityLevel,
    Urgency,
)
from app.modules.rag.chain import DiagnosisResult

logger = logging.getLogger(__name__)

# Urgency action plans per severity level
_URGENCY_PLANS = {
    "emergency": [
        "Call emergency services (112) immediately",
        "Do not drive yourself — get someone to take you or wait for ambulance",
        "Go to the nearest emergency room NOW",
    ],
    "urgent": [
        "See a doctor today — visit urgent care or emergency room",
        "Do not delay treatment",
        "If symptoms worsen, call 112 immediately",
    ],
    "moderate": [
        "Schedule a doctor appointment within 24–48 hours",
        "Monitor your symptoms closely",
        "If symptoms worsen significantly, seek immediate care",
    ],
    "low": [
        "Schedule a routine GP appointment within the next week",
        "Rest and stay hydrated",
        "Return if symptoms persist or worsen after 3 days",
    ],
}

_CALL_EMERGENCY_LEVELS = {"emergency"}

MEDICAL_DISCLAIMER = (
    "⚠️ This is AI-generated health information, not a medical diagnosis. "
    "Aarogya AI is not a substitute for professional medical advice. "
    "Always consult a qualified doctor before making any health decisions."
)


def build_response(
    context: PatientContext,
    diagnosis: DiagnosisResult,
    doctors: list[DoctorResult],
    processing_time_ms: int,
    urgency_override: dict = None,
    xgb_top_disease: str = None,
) -> AnalyzeResponse:
    """
    Assembles the final AnalyzeResponse.

    Args:
        context: PatientContext from patient_context.py
        diagnosis: DiagnosisResult from chain.run()
        doctors: List of DoctorResult from finder.find_doctors()
        processing_time_ms: Total elapsed time in milliseconds
        urgency_override: Optional ML urgency dict from severity_scorer.score_urgency().
                          If provided and ml_backed=True, ML urgency takes precedence
                          over RAG-inferred severity (critical for Emergency recall >= 0.95).
        xgb_top_disease: Top disease from XGBoost classifier (overrides context.primary_concern)

    Returns:
        Fully populated AnalyzeResponse
    """
    # Map severity string to enum (default moderate on unknown value)
    try:
        severity = SeverityLevel(diagnosis.severity_level)
    except ValueError:
        severity = SeverityLevel.moderate

    diagnosis_model = Diagnosis(
        condition_name=diagnosis.condition_name,
        confidence=round(diagnosis.confidence, 3),
        explanation=diagnosis.explanation,
        severity_level=severity,
        specialist_needed=diagnosis.specialist_needed,
        citations=diagnosis.citations,
    )

    # ML urgency override — LightGBM takes precedence over RAG severity
    # This is critical: Emergency recall >= 0.95 requires ML scorer to win
    if urgency_override and urgency_override.get("ml_backed"):
        try:
            ml_level = SeverityLevel(urgency_override["level"])
            # Always upgrade to EMERGENCY if ML says so (safety-critical)
            # Only downgrade from EMERGENCY if ML is also confident it's not emergency
            if ml_level == SeverityLevel.emergency or severity != SeverityLevel.emergency:
                severity_for_urgency = ml_level
            else:
                severity_for_urgency = severity  # Keep RAG emergency over ML downgrade
            logger.info(
                f"Urgency: RAG={severity.value} -> ML={urgency_override['level']} "
                f"(final={severity_for_urgency.value})"
            )
        except (ValueError, KeyError):
            severity_for_urgency = severity
    else:
        severity_for_urgency = severity

    # Use ML action plan if available, else fall back to default plan
    action_plan = (
        urgency_override.get("action_plan")
        if urgency_override and urgency_override.get("action_plan")
        else _URGENCY_PLANS.get(severity_for_urgency.value, _URGENCY_PLANS["moderate"])
    )

    urgency_model = Urgency(
        level=severity_for_urgency,
        action_plan=action_plan,
        call_emergency=severity_for_urgency.value in _CALL_EMERGENCY_LEVELS,
    )

    # Prefix disclaimer for emergency
    disclaimer = MEDICAL_DISCLAIMER
    if severity_for_urgency == SeverityLevel.emergency:
        disclaimer = "EMERGENCY — CALL 112 NOW! " + disclaimer

    # ── Primary concern priority: XGBoost → RAG → context ─────────────────
    # Never use raw symptom text — always prefer an actual disease name
    def _is_symptom_text(s: str) -> bool:
        """Heuristic: real disease names are short; symptom dumps are long."""
        return not s or len(s) > 60 or s.count(" ") > 6

    primary_concern = context.primary_concern
    if xgb_top_disease and not _is_symptom_text(xgb_top_disease):
        primary_concern = xgb_top_disease
    elif diagnosis.condition_name and not _is_symptom_text(diagnosis.condition_name):
        primary_concern = diagnosis.condition_name
    elif _is_symptom_text(primary_concern):
        # Last resort: extract first 4 words of context concern as placeholder
        words = (primary_concern or "").split()
        primary_concern = " ".join(words[:4]) if words else "symptoms under evaluation"

    return AnalyzeResponse(
        session_id=context.session_id,
        # Module 2 context fields
        context_built=True,
        inputs_processed=context.inputs_provided,
        symptoms_extracted=len(context.symptom_entities),
        risk_flags=context.risk_flags,
        context_confidence=round(context.context_confidence, 3),
        primary_concern=primary_concern,
        # Module 3+ diagnosis fields
        diagnosis=diagnosis_model,
        urgency=urgency_model,
        recommendations=doctors,
        disclaimer=disclaimer,
        processing_time_ms=processing_time_ms,
    )
