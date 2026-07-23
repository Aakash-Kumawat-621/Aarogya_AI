"""Doctors route — doctor/specialist finder endpoint (stub)."""

from fastapi import APIRouter

router = APIRouter(tags=["Doctors"])


@router.get("/doctors/search")
async def search_doctors() -> dict:
    """
    Find specialists near the user's location based on identified condition.
    
    TODO (Module 5): Implement Google Places API + NMC registry lookup.
    """
    return {"status": "not implemented", "module": "Module 5 will implement this"}


@router.get("/doctors/specialties")
async def list_specialties() -> dict:
    """Return all supported specialty mappings."""
    return {"status": "not implemented", "module": "Module 5 will implement this"}
