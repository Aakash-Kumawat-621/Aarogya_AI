"""
backend/app/modules/conversation/confidence_evaluator.py

Decides whether we have enough information to produce a final diagnosis
or need to ask follow-up questions.

Thresholds (from implementation plan):
  ≥ 0.70 top disease probability  → diagnose immediately
  0.40–0.70, ≤ 3 candidates       → ask 1 round of questions
  < 0.40 or > 3 candidates        → ask up to 2 rounds
  Any EMERGENCY signal detected   → skip questions, immediate emergency response
  turn ≥ MAX_TURNS                → force final diagnosis with uncertainty note
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

MAX_TURNS = 3
HIGH_CONFIDENCE_THRESHOLD = 0.70
MEDIUM_CONFIDENCE_THRESHOLD = 0.40

# EMERGENCY symptom/risk signals that bypass all follow-up
EMERGENCY_SIGNALS = frozenset({
    "cardiac_risk_critical",
    "emergency",
})

EMERGENCY_SYMPTOMS = frozenset({
    "chest_pain", "chest pain",
    "loss_of_consciousness",
    "slurred_speech",
    "facial_droop",
    "arm_weakness",
    "weakness_of_one_body_side",
    "coma",
    "stomach_bleeding",
})


def check_emergency_bypass(context) -> bool:
    """
    Returns True if any EMERGENCY signal is present — in which case we
    skip all follow-up questions and go straight to emergency response.
    """
    # Check risk flags
    risk_flags = set(context.risk_flags or [])
    if risk_flags & EMERGENCY_SIGNALS:
        logger.warning("Emergency bypass triggered by risk flag")
        return True

    # Check symptom entities
    symptom_names = {
        s.name.lower() for s in context.symptom_entities if not s.negated
    }
    if symptom_names & EMERGENCY_SYMPTOMS:
        logger.warning("Emergency bypass triggered by symptom")
        return True

    return False


def should_diagnose(
    xgb_predictions: list[dict],
    turn: int,
    context,
    urgency_result: Optional[dict] = None,
) -> tuple[bool, str]:
    """
    Decide whether to produce a final diagnosis or ask follow-up questions.

    Returns:
        (should_diagnose: bool, reason: str)
        - True  → proceed with full RAG chain diagnosis
        - False → generate follow-up questions for this turn
    """
    # Always bypass for emergency
    if check_emergency_bypass(context):
        return True, "emergency_bypass"

    # Urgency-level override
    if urgency_result and urgency_result.get("level") == "emergency":
        return True, "emergency_urgency"

    # Force diagnosis after max turns
    if turn >= MAX_TURNS:
        logger.info(f"Max turns ({MAX_TURNS}) reached — forcing final diagnosis")
        return True, "max_turns_reached"

    # No ML predictions → can't evaluate confidence, diagnose with what we have
    if not xgb_predictions:
        return True, "no_ml_predictions"

    top_prob = xgb_predictions[0].get("probability", 0.0)

    # High confidence → diagnose immediately
    if top_prob >= HIGH_CONFIDENCE_THRESHOLD:
        logger.info(f"High confidence ({top_prob:.2f}) — diagnosing immediately")
        return True, "high_confidence"

    # Medium confidence with low number of candidates → ask 1 round
    # If we've already asked that round (turn > 0) and still medium → diagnose
    candidate_count = len([p for p in xgb_predictions if p.get("probability", 0) > 0.15])
    if top_prob >= MEDIUM_CONFIDENCE_THRESHOLD:
        if turn > 0:
            logger.info(f"Medium confidence ({top_prob:.2f}), turn={turn} — diagnosing after follow-up")
            return True, "medium_confidence_after_followup"
        logger.info(f"Medium confidence ({top_prob:.2f}) — asking follow-up questions (turn 1)")
        return False, "medium_confidence_needs_followup"

    # Low confidence — ask up to 2 rounds
    if turn >= 2:
        logger.info(f"Low confidence ({top_prob:.2f}), turn={turn} ≥ 2 — forcing diagnosis")
        return True, "low_confidence_max_reached"

    logger.info(f"Low confidence ({top_prob:.2f}), {candidate_count} candidates — asking questions")
    return False, "low_confidence_needs_followup"


def get_confidence_note(reason: str, turn: int) -> Optional[str]:
    """
    Returns an optional disclaimer to append to the diagnosis when
    the analysis was forced due to insufficient information.
    """
    if reason == "max_turns_reached":
        return (
            "Note: This analysis is based on limited information after 3 rounds of questions. "
            "Please consult a doctor for a definitive diagnosis."
        )
    if reason == "low_confidence_max_reached":
        return (
            "Note: Your symptoms could match multiple conditions. "
            "This is a best-estimate based on available information. "
            "In-person medical evaluation is strongly recommended."
        )
    return None
