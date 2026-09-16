"""
backend/app/modules/conversation/session_manager.py

Manages multi-turn diagnostic session state.

Primary store:  DynamoDB (mediassist-sessions table, TTL 24h)
Fallback store: In-memory dict (for local dev / when DynamoDB is unavailable)

The in-memory store is process-local — sessions survive as long as the
Uvicorn worker is running. This is fine for development and single-server
deployments. For Lambda/multi-process deployments, DynamoDB must be configured.

Session state schema:
{
  "session_id": str,
  "session_type": "conversation",
  "status": "in_progress" | "complete" | "abandoned",
  "turn": int,
  "patient_profile": dict,
  "initial_symptoms_text": str,
  "accumulated_answers": dict,       # merged answers across all turns
  "accumulated_self_exams": dict,    # merged self-exam results across all turns
  "conversation_history": [...],     # full history of Q&A turns
  "differential_diagnoses": [...],   # last XGBoost top-3
  "current_top_prob": float,
  "final_diagnosis": dict | None,
  "expires_at": int (Unix timestamp)
}
"""

import copy
import logging
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

SESSION_TTL_HOURS = 24
TABLE_NAME = "mediassist-sessions"

# ── In-memory fallback store ──────────────────────────────────────────────────
# Used when DynamoDB is unavailable (dev mode, missing credentials, etc.)
_memory_store: dict[str, dict] = {}


# ── DynamoDB helpers ──────────────────────────────────────────────────────────

def _get_table():
    """Return the DynamoDB Table resource, or None if unavailable."""
    try:
        import boto3
        dynamodb = boto3.resource(
            "dynamodb",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        return dynamodb.Table(TABLE_NAME)
    except Exception as e:
        logger.debug(f"DynamoDB unavailable: {e}")
        return None


def _ddb_put(session: dict) -> bool:
    """Write a session to DynamoDB. Returns True on success."""
    try:
        import json
        from decimal import Decimal
        table = _get_table()
        if table is None:
            return False
        # DynamoDB requires Decimal instead of float — round-trip through JSON
        serialized = json.loads(
            json.dumps(session),
            parse_float=Decimal,
        )
        table.put_item(Item=serialized)
        return True
    except Exception as e:
        logger.warning(f"DynamoDB put failed: {e}")
        return False


def _ddb_get(session_id: str) -> Optional[dict]:
    """Read a session from DynamoDB. Returns None on failure or not found."""
    try:
        table = _get_table()
        if table is None:
            return None
        response = table.get_item(Key={"session_id": session_id})
        return response.get("Item")
    except Exception as e:
        logger.warning(f"DynamoDB get failed: {e}")
        return None


def _ddb_update_status(session_id: str, status: str, final_diagnosis: dict) -> bool:
    """Update session status in DynamoDB. Returns True on success."""
    try:
        table = _get_table()
        if table is None:
            return False
        table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET #status = :s, final_diagnosis = :d, completed_at = :t",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":s": status,
                ":d": final_diagnosis,
                ":t": int(time.time()),
            },
        )
        return True
    except Exception as e:
        logger.warning(f"DynamoDB update failed: {e}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def create_session(
    session_id: str,
    patient_profile: dict,
    initial_symptoms_text: str,
    differential_diagnoses: list[dict],
) -> dict:
    """
    Create a new conversation session.
    Tries DynamoDB first, falls back to in-memory store.
    Returns the created session dict.
    """
    expires_at = int(time.time()) + SESSION_TTL_HOURS * 3600

    session = {
        "session_id": session_id,
        "session_type": "conversation",
        "status": "in_progress",
        "turn": 0,
        "patient_profile": patient_profile,
        "initial_symptoms_text": initial_symptoms_text,
        "accumulated_answers": {},
        "accumulated_self_exams": {},
        "conversation_history": [],
        "differential_diagnoses": differential_diagnoses,
        "current_top_prob": (
            differential_diagnoses[0]["probability"] if differential_diagnoses else 0.0
        ),
        "final_diagnosis": None,
        "expires_at": expires_at,
        "created_at": int(time.time()),
    }

    # Try DynamoDB, always also store in-memory as safety net
    ddb_ok = _ddb_put(session)
    _memory_store[session_id] = copy.deepcopy(session)

    store_used = "DynamoDB + memory" if ddb_ok else "memory (DynamoDB unavailable)"
    logger.info(f"Conversation session created: {session_id} [{store_used}]")
    return session


def load_session(session_id: str) -> Optional[dict]:
    """
    Load a conversation session.
    Checks in-memory store first (fastest), then DynamoDB.
    Returns None if not found or expired.
    """
    # 1. Check in-memory store first
    session = _memory_store.get(session_id)
    if session:
        if session.get("expires_at", 0) < int(time.time()):
            logger.warning(f"In-memory session {session_id} expired")
            _memory_store.pop(session_id, None)
            return None
        logger.debug(f"Session {session_id} loaded from memory")
        return copy.deepcopy(session)

    # 2. Fall back to DynamoDB
    session = _ddb_get(session_id)
    if session:
        if session.get("expires_at", 0) < int(time.time()):
            logger.warning(f"DynamoDB session {session_id} expired")
            return None
        # Warm the in-memory cache
        _memory_store[session_id] = copy.deepcopy(session)
        logger.debug(f"Session {session_id} loaded from DynamoDB")
        return session

    logger.warning(f"Session {session_id} not found in memory or DynamoDB")
    return None


def append_turn(
    session_id: str,
    questions_asked: list[dict],
    self_exams_asked: list[dict],
    answers: dict,
    self_exam_results: dict,
    differential_diagnoses: list[dict],
) -> Optional[dict]:
    """
    Append a completed Q&A turn to the session and merge accumulated data.
    Returns updated session dict, or None if session not found.
    """
    session = load_session(session_id)
    if not session:
        return None

    # Only append a real turn record if there were actual answers
    if answers or self_exam_results:
        turn_record = {
            "turn": session["turn"] + 1,
            "questions_asked": questions_asked,
            "self_exams_asked": [e.get("id") for e in self_exams_asked],
            "answers": answers,
            "self_exam_results": self_exam_results,
            "timestamp": int(time.time()),
        }
        session["conversation_history"].append(turn_record)
        session["turn"] += 1

    # Always update differential and accumulated data
    session["accumulated_answers"].update(answers or {})
    session["accumulated_self_exams"].update(self_exam_results or {})
    if differential_diagnoses:
        session["differential_diagnoses"] = differential_diagnoses
        session["current_top_prob"] = differential_diagnoses[0]["probability"]
    session["expires_at"] = int(time.time()) + SESSION_TTL_HOURS * 3600

    # Persist: always update in-memory, try DynamoDB
    _memory_store[session_id] = copy.deepcopy(session)
    _ddb_put(session)

    logger.info(f"Session {session_id} updated — turn {session['turn']}")
    return session


def complete_session(session_id: str, final_diagnosis: dict) -> None:
    """Mark a session as complete with the final diagnosis."""
    # Update in-memory first
    if session_id in _memory_store:
        _memory_store[session_id]["status"] = "complete"
        _memory_store[session_id]["final_diagnosis"] = final_diagnosis
        _memory_store[session_id]["completed_at"] = int(time.time())

    # Try DynamoDB
    _ddb_update_status(session_id, "complete", final_diagnosis)
    logger.info(f"Session {session_id} marked complete")


def build_enriched_symptoms_text(session: dict) -> str:
    """
    Merge initial symptoms + all accumulated answers + self-exam results
    into an enriched text representation for the NLP/RAG pipeline.

    Example output:
      "chest pain and sweating. Pain is dull/pressure. Radiates to arm: yes.
       Pulse Rate: 108 bpm. Pain Scale: 8/10."
    """
    parts = [session.get("initial_symptoms_text", "").rstrip(".")]

    answers = session.get("accumulated_answers", {})
    for answer in answers.values():
        if answer and str(answer).strip():
            parts.append(str(answer).strip())

    self_exams = session.get("accumulated_self_exams", {})
    for exam_id, result in self_exams.items():
        if result is not None and str(result).strip():
            exam_label = exam_id.replace("_", " ").title()
            parts.append(f"{exam_label}: {result}")

    return ". ".join(p for p in parts if p.strip()) + "."
