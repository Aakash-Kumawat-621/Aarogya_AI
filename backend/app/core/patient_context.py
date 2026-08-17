"""
backend/app/core/patient_context.py

Merges all 5 input modalities into a unified PatientContext object.
Runs all IO-bound operations in parallel using asyncio.gather.
"""

import asyncio
import logging
import uuid
from typing import List, Optional

from pydantic import BaseModel

from app.models.request_models import LocationData, PatientProfile
from app.modules.image.image_preprocessor import preprocess_xray
from app.modules.nlp.preprocessor import extract_symptoms
from app.modules.nlp.symptom_normalizer import normalize_all
from app.modules.ocr.textract_handler import extract_prescription
from app.services.bedrock_service import analyze_body_photo
from app.services.s3_service import upload_file

logger = logging.getLogger(__name__)


class SymptomEntity(BaseModel):
    name: str
    canonical_form: Optional[str] = None
    negated: bool = False
    duration: Optional[str] = None


class XrayResult(BaseModel):
    s3_key: str
    findings: List[str] = []


class PatientContext(BaseModel):
    session_id: str
    patient_profile: PatientProfile
    location: Optional[LocationData] = None
    inputs_provided: List[str] = []
    context_confidence: float = 0.3
    symptom_entities: List[SymptomEntity] = []
    disease_history_mentions: List[str] = []
    xray_findings: Optional[XrayResult] = None
    body_photo_findings: Optional[dict] = None
    prescription_data: Optional[dict] = None
    risk_flags: List[str] = []
    primary_concern: Optional[str] = None


async def _process_symptoms(text: str):
    """Extract and normalize symptoms from free text (runs NLP in thread pool)."""
    try:
        # Wrap CPU-bound tasks so they don't block the event loop
        entities = await asyncio.to_thread(extract_symptoms, text)
        normalized = await asyncio.to_thread(normalize_all, entities)
        return normalized
    except Exception as e:
        logger.error(f"Error processing symptoms: {e}")
        return []


async def _process_xray(image_bytes: bytes):
    """Upload X-ray to S3 and run CLAHE preprocessing (classifier is Module 4)."""
    try:
        filename = f"xray_{uuid.uuid4().hex}.jpg"
        s3_key = await asyncio.to_thread(
            upload_file, image_bytes, filename, "image/jpeg"
        )
        # Validate that CLAHE works; full classifier logic comes in Module 4
        await asyncio.to_thread(preprocess_xray, image_bytes)
        return XrayResult(s3_key=s3_key, findings=["X-ray uploaded for analysis"])
    except Exception as e:
        logger.error(f"Error processing X-ray: {e}")
        return None


async def _process_body_photo(image_bytes: bytes):
    """Analyze body photo via Bedrock vision model."""
    try:
        return await asyncio.to_thread(analyze_body_photo, image_bytes)
    except Exception as e:
        logger.error(f"Error processing body photo: {e}")
        return None


async def _process_prescription(image_bytes: bytes):
    """Extract prescription data via AWS Textract."""
    try:
        return await asyncio.to_thread(extract_prescription, image_bytes)
    except Exception as e:
        logger.error(f"Error processing prescription: {e}")
        return None


async def build_patient_context(
    symptoms_text: Optional[str],
    patient_profile: PatientProfile,
    location: Optional[LocationData] = None,
    xray_bytes: Optional[bytes] = None,
    body_photo_bytes: Optional[bytes] = None,
    prescription_bytes: Optional[bytes] = None,
) -> PatientContext:
    """Builds a unified PatientContext from all 5 modalities in parallel."""
    session_id = uuid.uuid4().hex

    # Map each modality name to its coroutine (skip if no data provided)
    tasks = {
        "symptoms": _process_symptoms(symptoms_text) if symptoms_text else None,
        "xray": (
            _process_xray(xray_bytes) if xray_bytes else None
        ),  # fixed: was kray_bytes
        "body_photo": (
            _process_body_photo(body_photo_bytes) if body_photo_bytes else None
        ),
        "prescription": (
            _process_prescription(prescription_bytes) if prescription_bytes else None
        ),
    }

    # Run all active tasks in parallel
    active_keys = [k for k, v in tasks.items() if v is not None]
    active_coros = [v for v in tasks.values() if v is not None]
    results = await asyncio.gather(*active_coros, return_exceptions=True)
    result_map = dict(zip(active_keys, results))

    # Parse symptom entities
    raw_symptoms = result_map.get("symptoms") or []
    if isinstance(raw_symptoms, Exception):
        raw_symptoms = []

    symptom_objs = []
    for e in raw_symptoms:
        if isinstance(e, dict):
            symptom_objs.append(
                SymptomEntity(
                    name=e.get("entity", e.get("name", "")),
                    canonical_form=e.get("canonical_form"),
                    negated=e.get("negated", False),
                    duration=e.get("duration"),
                )
            )

    # Track which input modalities were provided
    inputs_provided = []
    if symptoms_text:
        inputs_provided.append("symptoms")
    if xray_bytes:
        inputs_provided.append("xray")
    if body_photo_bytes:
        inputs_provided.append("body_photo")
    if prescription_bytes:
        inputs_provided.append("prescription")

    # Confidence: 0.3 base + 0.15 per modality (capped at 1.0)
    confidence = min(0.3 + (len(inputs_provided) * 0.15), 1.0)

    # Risk flag logic
    risk_flags = []
    if patient_profile.age > 50:
        risk_flags.append("age_over_50")
    if getattr(patient_profile, "smoking", None) == "current":
        risk_flags.append("current_smoker")

    cardiac_keywords = {
        "chest pain",
        "palpitations",
        "shortness of breath",
        "dizziness",
    }
    active_symptom_names = {s.name.lower() for s in symptom_objs if not s.negated}
    if active_symptom_names & cardiac_keywords:
        if "age_over_50" in risk_flags or "current_smoker" in risk_flags:
            risk_flags.append("cardiac_risk_critical")

    # Primary concern: first non-negated symptom
    active_symptoms = [s for s in symptom_objs if not s.negated]
    primary_concern = active_symptoms[0].name if active_symptoms else None

    return PatientContext(
        session_id=session_id,
        patient_profile=patient_profile,
        location=location,
        inputs_provided=inputs_provided,
        context_confidence=confidence,
        symptom_entities=symptom_objs,
        xray_findings=result_map.get("xray"),
        body_photo_findings=result_map.get("body_photo"),
        prescription_data=result_map.get("prescription"),
        risk_flags=risk_flags,
        primary_concern=primary_concern,
    )
