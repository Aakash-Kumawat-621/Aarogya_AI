"""Health check route — always returns 200 OK."""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict:
    """Liveness probe — used by Lambda, load balancers, and the frontend."""
    return {
        "status": "ok",
        "service": "aarogya-ai",
        "version": "0.1.0",
    }
