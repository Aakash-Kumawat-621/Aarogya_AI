"""Feedback route — user feedback submission endpoint (stub)."""

from fastapi import APIRouter

router = APIRouter(tags=["Feedback"])


@router.post("/feedback")
async def submit_feedback() -> dict:
    """
    Accept user feedback on analysis quality.
    Stored in DynamoDB for future model improvement.
    
    TODO (Module 5): Implement feedback storage.
    """
    return {"status": "not implemented", "module": "Module 5 will implement this"}
