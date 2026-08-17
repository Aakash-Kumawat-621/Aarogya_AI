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
) -> str:
    """
    Assembles the user-turn message combining patient context + retrieved chunks.
    """
    # Patient summary
    profile = context.patient_profile
    active_symptoms = [s for s in context.symptom_entities if not s.negated]
    symptom_list = ", ".join(s.canonical_form or s.name for s in active_symptoms) or "none reported"

    patient_summary = (
        f"Patient: {profile.age}-year-old {getattr(profile, 'gender', 'patient') or 'patient'}\n"
        f"Symptoms: {symptom_list}\n"
        f"Risk flags: {', '.join(context.risk_flags) or 'none'}\n"
        f"Known conditions: {', '.join(getattr(profile, 'conditions', None) or []) or 'none'}\n"
        f"Smoking: {getattr(profile, 'smoking', 'unknown') or 'unknown'}\n"
        f"Context confidence: {context.context_confidence:.2f}"
    )

    # Format retrieved medical chunks
    medical_text = ""
    for i, chunk in enumerate(retrieved.get("medical_chunks", []), 1):
        pmid = chunk.get("pmid", "N/A")
        source = chunk.get("source", "unknown")
        category = chunk.get("disease_category", "")
        medical_text += (
            f"\n[{i}] PMID:{pmid} | Source:{source} | Category:{category}\n"
            f"{chunk.get('text', '')}\n"
        )

    # Format drug chunks
    drug_text = ""
    for chunk in retrieved.get("drug_chunks", []):
        drug_name = chunk.get("drug_name", "")
        drug_text += f"\nDrug: {drug_name}\n{chunk.get('text', '')}\n"

    return (
        f"PATIENT CONTEXT:\n{patient_summary}\n\n"
        f"RETRIEVED MEDICAL KNOWLEDGE:{medical_text or ' (no relevant chunks found)'}\n\n"
        f"DRUG DATABASE:{drug_text or ' (no relevant drug info found)'}\n\n"
        "Based ONLY on the above, provide your structured health information response."
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
                logger.warning(f"Bedrock throttled — retrying in {wait}s")
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

    # Safety override: if cardiac_risk_critical + chest pain → always emergency
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

def run(context: PatientContext) -> DiagnosisResult:
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
    prompt = _build_prompt(context, retrieved)

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
