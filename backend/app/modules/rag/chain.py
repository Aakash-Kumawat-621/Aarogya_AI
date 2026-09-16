"""
backend/app/modules/rag/chain.py

The RAG orchestrator for Aarogya AI.

Flow:
  PatientContext
    → query_builder.build_query()        (rich query string)
    → retriever.retrieve()               (BioSentBERT + Pinecone hybrid)
    → _build_prompt()                    (medical system prompt + chunks)
    → Bedrock Nova Lite                  (text generation)
    → _parse_response()                  (validate DiagnosisResult JSON)
    → DiagnosisResult
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.core.patient_context import PatientContext
from app.modules.rag import query_builder, retriever

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output data class
# ---------------------------------------------------------------------------

@dataclass
class DiagnosisResult:
    """Structured diagnosis output from the RAG chain."""
    condition_name: str
    confidence: float                   # 0.0 – 1.0
    explanation: str                    # Plain-English for the patient
    severity_level: str                 # "low" | "moderate" | "urgent" | "emergency"
    specialist_needed: str
    citations: List[str] = field(default_factory=list)   # PMIDs cited
    requires_emergency_attention: bool = False
    drug_interactions_noted: List[str] = field(default_factory=list)
    retrieval_method: str = "dense"
    top_retrieval_score: float = 0.0


# ---------------------------------------------------------------------------
# Medical System Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are Aarogya AI — a medical information assistant.
You are NOT a doctor. You do NOT diagnose patients.
You provide evidence-based health information to help people understand their
symptoms and seek appropriate care.

RULES — follow ALL of these strictly:
1. Never say "you have [disease]" — say "symptoms consistent with" or "possible"
2. Never recommend specific prescription drugs by name
3. Always set requires_emergency_attention=true if the patient has
   cardiac_risk_critical in their risk flags AND reports chest pain or palpitations
4. Only use facts from the RETRIEVED MEDICAL KNOWLEDGE section below
5. If retrieved chunks do not clearly address the symptoms, acknowledge uncertainty
6. Cite the PMID of every factual claim you make
7. Return ONLY valid JSON — no prose outside the JSON, no markdown code fences

SEVERITY LEVELS:
- "low": symptoms manageable at home, see GP within a week
- "moderate": see a doctor within 24-48 hours
- "urgent": see a doctor today / go to urgent care
- "emergency": call emergency services / go to ER immediately

OUTPUT FORMAT — return exactly this JSON schema (no other text):
{
  "condition_name": "string (most likely condition, 2-5 words)",
  "confidence": 0.0,
  "explanation": "string (plain English, 2-4 sentences, suitable for patient)",
  "severity_level": "low|moderate|urgent|emergency",
  "specialist_needed": "string (specialist type)",
  "citations": ["pmid1", "pmid2"],
  "requires_emergency_attention": false,
  "drug_interactions_noted": []
}"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(
    context: PatientContext,
    retrieved: dict,
    ml_predictions: dict = None,
) -> str:
    """
    Assembles the user-turn message combining patient context + retrieved chunks + ML predictions.
    Includes full patient demographics, comorbidities, and all top-3 ML candidates.
    """
    profile = context.patient_profile
    active_symptoms = [s for s in context.symptom_entities if not s.negated]
    negated_symptoms = [s for s in context.symptom_entities if s.negated]

    # Build detailed symptom description including severity and duration
    symptom_details = []
    for s in active_symptoms:
        detail = s.canonical_form or s.name
        extras = []
        if getattr(s, "severity", None):
            extras.append(s.severity)
        if getattr(s, "duration", None):
            extras.append(f"for {s.duration}")
        if getattr(s, "duration_category", None):
            extras.append(f"({s.duration_category})")
        if extras:
            detail += f" [{', '.join(extras)}]"
        symptom_details.append(detail)
    symptom_list = ", ".join(symptom_details) or "none reported"
    negated_list = ", ".join(s.name for s in negated_symptoms) or "none"

    # Build full patient profile section
    age = getattr(profile, "age", "unknown")
    gender = getattr(profile, "gender", "patient") or "patient"
    smoking = getattr(profile, "smoking", "unknown") or "unknown"
    pack_years = getattr(profile, "pack_years", None)
    alcohol = getattr(profile, "alcohol_units_per_week", None)
    activity = getattr(profile, "activity_level", None)
    sleep = getattr(profile, "sleep_hours", None)
    conditions = getattr(profile, "conditions", None) or []
    medications = getattr(profile, "medications", None) or []
    allergies = getattr(profile, "allergies", None) or []
    family_hx = getattr(profile, "family_history", None) or []

    # BMI calculation
    height = getattr(profile, "height_cm", None)
    weight = getattr(profile, "weight_kg", None)
    bmi_str = "unknown"
    if height and weight and height > 0:
        bmi = weight / ((height / 100) ** 2)
        bmi_str = f"{bmi:.1f}"

    patient_section = (
        f"PATIENT PROFILE:\n"
        f"  Age: {age} | Gender: {gender} | BMI: {bmi_str}\n"
        f"  Smoking: {smoking}" + (f" ({pack_years} pack-years)" if pack_years else "") + "\n"
        f"  Alcohol: {f'{alcohol} units/week' if alcohol is not None else 'unknown'}\n"
        f"  Activity level: {activity or 'unknown'} | Sleep: {f'{sleep}h/night' if sleep else 'unknown'}\n"
        f"  Known conditions: {', '.join(conditions) or 'none'}\n"
        f"  Medications: {', '.join(medications) or 'none'}\n"
        f"  Allergies: {', '.join(allergies) or 'none'}\n"
        f"  Family history: {', '.join(family_hx) or 'none'}\n"
        f"  Risk flags: {', '.join(context.risk_flags) or 'none'}\n"
    )

    symptom_section = (
        f"SYMPTOMS REPORTED:\n"
        f"  Active: {symptom_list}\n"
        f"  Denied: {negated_list}\n"
    )

    # ML predictions section — include all top-3 with probabilities
    ml_section = ""
    if ml_predictions:
        top3 = ml_predictions.get("xgb_top3", [])
        xgb_summary = ""
        if top3:
            xgb_summary = "  XGBoost disease candidates:\n"
            for i, pred in enumerate(top3, 1):
                disease = pred.get("disease", "Unknown")
                prob = pred.get("probability", 0.0)
                xgb_summary += f"    {i}. {disease} (probability: {prob:.1%})\n"
        else:
            xgb_summary = "  XGBoost: no predictions available\n"

        urgency = ml_predictions.get("urgency_level", "N/A")
        xray = ml_predictions.get("xray_top_condition")

        # Ensemble signal: check if XGBoost top-1 and retrieved KB both suggest same condition
        xgb_top = (top3[0]["disease"] if top3 else "").lower()
        rag_categories = [
            c.get("disease_category", "").lower()
            for c in retrieved.get("medical_chunks", [])
        ]
        ensemble_agreement = any(xgb_top in cat for cat in rag_categories if cat)

        ml_section = (
            f"MACHINE LEARNING PREDICTIONS:\n"
            f"{xgb_summary}"
            f"  Computed urgency (LightGBM/rule-based): {urgency}\n"
            + (f"  X-ray model finding: {xray}\n" if xray else "")
            + (f"  ⚡ Ensemble signal: XGBoost and retrieved KB both suggest similar condition — higher confidence warranted.\n"
               if ensemble_agreement else "")
        )

    # Format retrieved medical chunks
    medical_text = ""
    for i, chunk in enumerate(retrieved.get("medical_chunks", []), 1):
        pmid = chunk.get("pmid", "N/A")
        source = chunk.get("source", "unknown")
        category = chunk.get("disease_category", "")
        score = chunk.get("score", 0.0)
        medical_text += (
            f"\n[{i}] PMID:{pmid} | Source:{source} | Category:{category} | Relevance:{score:.3f}\n"
            f"{chunk.get('text', '')}\n"
        )

    # Format drug chunks
    drug_text = ""
    for chunk in retrieved.get("drug_chunks", []):
        drug_name = chunk.get("drug_name", "")
        drug_text += f"\nDrug: {drug_name}\n{chunk.get('text', '')}\n"

    return (
        f"{patient_section}\n"
        f"{symptom_section}\n"
        f"{ml_section}\n"
        f"RETRIEVED MEDICAL KNOWLEDGE:{medical_text or ' (no relevant chunks found)'}\n\n"
        f"DRUG DATABASE:{drug_text or ' (no relevant drug info found)'}\n\n"
        "Based ONLY on the above evidence, provide your structured health information response. "
        "Incorporate the ML predictions where they are clinically reasonable given the patient context. "
        "Pay particular attention to the patient's age, comorbidities, medications, and risk flags when "
        "assessing severity and specialist recommendation."
    )


def _call_bedrock(prompt: str, max_retries: int = 3) -> str:
    """
    Calls Bedrock Nova Lite with the assembled prompt.
    Returns the raw text content from the model response.
    """
    client = boto3.client("bedrock-runtime", **settings.boto3_kwargs)
    body = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "system": [{"text": _SYSTEM_PROMPT}],
        "inferenceConfig": {
            "maxTokens": 1024,
            "temperature": 0.1,   # Low temperature for consistent medical output
            "topP": 0.9,
        },
    }

    for attempt in range(max_retries):
        try:
            response = client.invoke_model(
                modelId=settings.BEDROCK_DIAGNOSIS_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            resp_body = json.loads(response["body"].read())
            return resp_body["output"]["message"]["content"][0]["text"]
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ThrottlingException" and attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Bedrock throttled - retrying in {wait}s")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Bedrock call failed after all retries")


def _parse_response(text: str, context: PatientContext) -> DiagnosisResult:
    """
    Parses the Bedrock JSON response into a DiagnosisResult.
    Falls back gracefully on parse errors.
    """
    # Strip markdown fences if the model added them anyway
    cleaned = text.strip().strip("```json").strip("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse Bedrock JSON response: {text[:300]}")
        return DiagnosisResult(
            condition_name="Unable to determine",
            confidence=0.1,
            explanation=(
                "We were unable to process your symptoms at this time. "
                "Please consult a doctor directly."
            ),
            severity_level="moderate",
            specialist_needed="General Physician",
        )

    # Safety override: if cardiac_risk_critical + chest pain +' always emergency
    active = {s.canonical_form or s.name for s in context.symptom_entities if not s.negated}
    cardiac_symptoms = {"chest pain", "palpitations", "shortness of breath"}
    if "cardiac_risk_critical" in context.risk_flags and active & cardiac_symptoms:
        data["requires_emergency_attention"] = True
        data["severity_level"] = "emergency"

    return DiagnosisResult(
        condition_name=data.get("condition_name", "Unknown condition"),
        confidence=min(max(float(data.get("confidence", 0.5)), 0.0), 1.0),
        explanation=data.get("explanation", ""),
        severity_level=data.get("severity_level", "moderate"),
        specialist_needed=data.get("specialist_needed", "General Physician"),
        citations=data.get("citations", []),
        requires_emergency_attention=bool(data.get("requires_emergency_attention", False)),
        drug_interactions_noted=data.get("drug_interactions_noted", []),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(context: PatientContext, ml_predictions: dict = None) -> DiagnosisResult:
    """
    Executes the full RAG chain for a given PatientContext.

    Steps:
      1. Build rich query from context
      2. Retrieve relevant medical + drug chunks (hybrid search)
      3. Assemble prompt
      4. Call Bedrock Nova Lite
      5. Parse and validate response

    Args:
        context: Fully assembled PatientContext from patient_context.py
        ml_predictions: Optional dict containing XGBoost/LightGBM outputs

    Returns:
        DiagnosisResult with condition, confidence, severity, specialist
    """
    t0 = time.time()

    # 1. Build query
    query = query_builder.build_query(context)
    logger.info(f"RAG query: {query[:120]}…")

    # 2. Retrieve chunks
    retrieved = retriever.retrieve(query, top_k=5)

    # 3. Build prompt
    prompt = _build_prompt(context, retrieved, ml_predictions)

    # 4. Call Bedrock
    raw_response = _call_bedrock(prompt)

    # 5. Parse
    result = _parse_response(raw_response, context)
    result.retrieval_method = retrieved["retrieval_method"]
    result.top_retrieval_score = retrieved["top_score"]

    elapsed = int((time.time() - t0) * 1000)
    logger.info(
        f"RAG chain complete in {elapsed}ms — "
        f"{result.condition_name} (confidence={result.confidence:.2f}, "
        f"severity={result.severity_level})"
    )
    return result
