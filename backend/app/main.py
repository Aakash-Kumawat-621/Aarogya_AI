"""Aarogya AI Backend — FastAPI Application Entry Point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.routes import analyze, doctors, feedback, health, history
from app.config import settings

app = FastAPI(
    title="Aarogya AI",
    description="Multimodal medical intelligence API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten to Lovable URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(health.router,   prefix="/api/v1")
app.include_router(analyze.router,  prefix="/api/v1")
app.include_router(doctors.router,  prefix="/api/v1")
app.include_router(history.router,  prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")

# ── AWS Lambda handler ─────────────────────────────────────────────────────────
handler = Mangum(app, lifespan="off")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
