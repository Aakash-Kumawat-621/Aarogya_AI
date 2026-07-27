import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.routes import analyze, doctors, feedback, health, history

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Aarogya AI", version="1.0.0", description="Backend API for Aarogya AI"
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("Aarogya AI started")


# Register routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(analyze.router, prefix="/api/v1")
app.include_router(doctors.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")

# Mangum handler for AWS Lambda
handler = Mangum(app, lifespan="off")
