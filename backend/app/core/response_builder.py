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
) -> AnalyzeResponse:
    """
    Assembles the final AnalyzeResponse.

    Args:
        context: PatientContext from patient_context.py
        diagnosis: DiagnosisResult from chain.run()
        doctors: List of DoctorResult from finder.find_doctors()
        processing_time_ms: Total elapsed time in milliseconds

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

    urgency_model = Urgency(
        level=severity,
        action_plan=_URGENCY_PLANS.get(severity.value, _URGENCY_PLANS["moderate"]),
        call_emergency=severity.value in _CALL_EMERGENCY_LEVELS,
    )

    return AnalyzeResponse(
        session_id=context.session_id,
        # Module 2 context fields
        context_built=True,
        inputs_processed=context.inputs_provided,
        symptoms_extracted=len(context.symptom_entities),
        risk_flags=context.risk_flags,
        context_confidence=round(context.context_confidence, 3),
        primary_concern=context.primary_concern,
        # Module 3 diagnosis fields
        diagnosis=diagnosis_model,
        urgency=urgency_model,
        recommendations=doctors,
        disclaimer=MEDICAL_DISCLAIMER,
        processing_time_ms=processing_time_ms,
    )
