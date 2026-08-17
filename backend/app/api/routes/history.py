import logging

from fastapi import APIRouter, HTTPException

from app.services.dynamodb_service import get_session

router = APIRouter(tags=["History"])
logger = logging.getLogger(__name__)


@router.get("/history/{session_id}")
async def get_session_history(session_id: str):
    """
    Retrieves a past analysis session by session ID.

    Returns the saved PatientContext and DiagnosisResult from DynamoDB.
    Session data is retained for 30 days (TTL).
    """
    if not session_id or len(session_id) < 8:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    session = get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or has expired (30-day TTL)",
        )

    return {
        "session_id": session_id,
        "created_at": session.get("created_at"),
        "context": session.get("context"),
        "diagnosis": session.get("diagnosis"),
    }
