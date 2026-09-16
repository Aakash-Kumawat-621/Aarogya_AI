"""
backend/app/modules/conversation/question_generator.py

Uses Bedrock Nova Lite to generate targeted follow-up questions that
differentiate between competing differential diagnoses.

Input:  differential diagnoses (top-3 from XGBoost), patient context
Output: 2-3 structured FollowUpQuestion objects + list of self-exam IDs

The questions are designed to be:
- Binary yes/no OR simple multiple-choice (max 4 options)
- Clinically meaningful (directly distinguishing between the candidates)
- In plain English that a layperson can understand
"""

import json
import logging
import time

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

_QUESTION_SYSTEM_PROMPT = """You are a medical triage assistant helping to narrow down a patient's diagnosis
by asking targeted follow-up questions.

You will receive:
1. The patient's initial symptoms and profile
2. A list of top differential diagnoses with their probabilities
3. A list of available self-examination IDs

Your task is to generate:
- 2 to 3 follow-up questions that would BEST distinguish between the differential diagnoses
- 0 to 2 self-examination IDs from the provided list that would provide discriminating clinical data

RULES:
- Questions must be in plain English (8th-grade reading level)
- Each question must be either yes_no or multiple_choice (max 4 options)
- Do NOT ask about symptoms already reported
- Do NOT suggest any prescription medication or specific treatment
- Focus on questions with HIGH diagnostic value (separating the most likely conditions)
- If the patient mentions ANY emergency symptom (chest pain radiating to arm, sudden severe headache,
  facial droop, one-sided weakness), include "emergency_flag": true in your response

OUTPUT: Return ONLY valid JSON, no prose, no markdown fences:
{
  "emergency_flag": false,
  "reasoning": "Brief explanation of why these questions were chosen",
  "questions": [
    {
      "id": "q1",
      "text": "Is the chest pain...",
      "type": "yes_no",
      "options": null
    },
    {
      "id": "q2",
      "text": "Which best describes...",
      "type": "multiple_choice",
      "options": ["Option A", "Option B", "Option C", "Option D"]
    }
  ],
  "recommended_self_exams": ["pulse_rate", "skin_color"]
}"""


def generate_followup_questions(
    context,
    xgb_predictions: list[dict],
    turn: int,
    available_exam_ids: list[str],
) -> dict:
    """
    Call Bedrock to generate targeted follow-up questions for the current turn.

    Args:
        context: PatientContext with symptoms, profile, risk flags
        xgb_predictions: Top-3 disease predictions from XGBoost
        turn: Current conversation turn number (1-indexed)
        available_exam_ids: IDs of self-exams available in our library

    Returns:
        {
          "emergency_flag": bool,
          "reasoning": str,
          "questions": [{"id", "text", "type", "options"}, ...],
          "recommended_self_exams": [exam_dict, ...]   <- full exam objects
        }
    """
    from app.modules.conversation.self_exam_guide import (
        SELF_EXAM_LIBRARY,
        get_exams_for_differential,
    )

    profile = context.patient_profile
    active_symptoms = [s for s in context.symptom_entities if not s.negated]
    symptom_list = ", ".join(s.canonical_form or s.name for s in active_symptoms) or "not specified"

    # Build differentials summary
    differentials_text = ""
    for i, pred in enumerate(xgb_predictions[:3], 1):
        disease = pred.get("disease", "Unknown")
        prob = pred.get("probability", 0.0)
        differentials_text += f"  {i}. {disease} (probability: {prob:.1%})\n"

    prompt = (
        f"PATIENT:\n"
        f"  Age: {getattr(profile, 'age', '?')}, "
        f"Gender: {getattr(profile, 'gender', '?')}, "
        f"Smoking: {getattr(profile, 'smoking', 'unknown')}\n"
        f"  Known conditions: {', '.join(getattr(profile, 'conditions', []) or []) or 'none'}\n"
        f"  Risk flags: {', '.join(context.risk_flags) or 'none'}\n\n"
        f"SYMPTOMS ALREADY REPORTED:\n  {symptom_list}\n\n"
        f"DIFFERENTIAL DIAGNOSES (top candidates):\n{differentials_text}\n"
        f"CONVERSATION TURN: {turn} (max 3 turns total)\n\n"
        f"AVAILABLE SELF-EXAM IDs: {json.dumps(available_exam_ids)}\n\n"
        f"Generate targeted follow-up questions to distinguish between these diagnoses."
    )

    try:
        client = boto3.client("bedrock-runtime", **settings.boto3_kwargs)
        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "system": [{"text": _QUESTION_SYSTEM_PROMPT}],
            "inferenceConfig": {
                "maxTokens": 800,
                "temperature": 0.2,
                "topP": 0.9,
            },
        }

        for attempt in range(3):
            try:
                response = client.invoke_model(
                    modelId=settings.BEDROCK_DIAGNOSIS_MODEL_ID,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(body),
                )
                raw = json.loads(response["body"].read())
                text = raw["output"]["message"]["content"][0]["text"]
                break
            except ClientError as e:
                if e.response["Error"]["Code"] == "ThrottlingException" and attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    raise

        # Parse Bedrock response
        cleaned = text.strip().strip("```json").strip("```").strip()
        data = json.loads(cleaned)

        # Attach full self-exam objects for the recommended exams
        recommended_ids = data.get("recommended_self_exams", [])
        # Also add condition-based exams not already included
        condition_exams = get_exams_for_differential(
            [p.get("disease", "") for p in xgb_predictions[:3]]
        )
        condition_exam_ids = [e["id"] for e in condition_exams]

        # Merge: recommended by Bedrock + condition-based, deduplicated, max 3
        all_exam_ids: list[str] = []
        seen: set[str] = set()
        for eid in recommended_ids + condition_exam_ids:
            if eid not in seen and eid in SELF_EXAM_LIBRARY:
                seen.add(eid)
                all_exam_ids.append(eid)
            if len(all_exam_ids) >= 3:
                break

        data["recommended_self_exams"] = [
            SELF_EXAM_LIBRARY[eid] for eid in all_exam_ids
        ]

        logger.info(
            f"Generated {len(data.get('questions', []))} follow-up questions, "
            f"{len(data['recommended_self_exams'])} self-exams "
            f"(emergency_flag={data.get('emergency_flag', False)})"
        )
        return data

    except Exception as e:
        logger.error(f"Question generation failed: {e} — using fallback questions")
        return _fallback_questions(xgb_predictions, available_exam_ids)


def _fallback_questions(xgb_predictions: list[dict], available_exam_ids: list[str]) -> dict:
    """
    Static fallback questions when Bedrock is unavailable.
    """
    from app.modules.conversation.self_exam_guide import SELF_EXAM_LIBRARY

    return {
        "emergency_flag": False,
        "reasoning": "Fallback questions (Bedrock unavailable)",
        "questions": [
            {
                "id": "q1",
                "text": "On a scale of 1-10, how severe is your current discomfort?",
                "type": "multiple_choice",
                "options": ["1-3 (mild)", "4-6 (moderate)", "7-9 (severe)", "10 (worst ever)"],
            },
            {
                "id": "q2",
                "text": "How long have you been experiencing these symptoms?",
                "type": "multiple_choice",
                "options": [
                    "Less than 1 hour",
                    "1–24 hours",
                    "1–7 days",
                    "More than 1 week",
                ],
            },
            {
                "id": "q3",
                "text": "Do the symptoms come and go, or are they constant?",
                "type": "multiple_choice",
                "options": ["Constant", "Come and go", "Getting worse", "Getting better"],
            },
        ],
        "recommended_self_exams": [
            SELF_EXAM_LIBRARY["pulse_rate"],
            SELF_EXAM_LIBRARY["pain_scale"],
        ],
    }
