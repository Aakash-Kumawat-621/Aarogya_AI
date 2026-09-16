"""
backend/app/main.py

FastAPI application entry point — Aarogya AI.

Module 6 additions:
  - Sentry SDK (error tracking, stack traces, AWS Lambda integration)
  - SlowAPI rate limiting (10 req/min on /analyze, 30/min on /doctors/search)
  - CORS locked to ALLOWED_ORIGIN in production (wildcard only in dev)
"""

import logging

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import analyze, conversation, doctors, feedback, health, history
from app.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

# ── Sentry ────────────────────────────────────────────────────────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[
            StarletteIntegration(transaction_style="url"),
            FastApiIntegration(transaction_style="url"),
        ],
        traces_sample_rate=0.1,          # 10% of requests traced (performance)
        environment=settings.APP_ENV,
        send_default_pii=False,          # Don't send patient PII to Sentry
    )
    logger.info(f"Sentry initialized for env={settings.APP_ENV}")
else:
    logger.warning("SENTRY_DSN not set — error tracking disabled")

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Aarogya AI",
    version="1.0.0",
    description="AI-powered medical diagnostic assistant",
)

# Attach rate limiter state + error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Dev: allow all origins | Production: lock to ALLOWED_ORIGIN
if settings.is_production:
    cors_origins = [settings.ALLOWED_ORIGIN]
    logger.info(f"CORS locked to: {settings.ALLOWED_ORIGIN}")
else:
    cors_origins = ["*"]
    logger.info("CORS: allowing all origins (development mode)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info(f"Aarogya AI started | env={settings.APP_ENV}")


# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(health.router,        prefix="/api/v1")
app.include_router(analyze.router,       prefix="/api/v1")
app.include_router(conversation.router,  prefix="/api/v1")
app.include_router(doctors.router,       prefix="/api/v1")
app.include_router(history.router,       prefix="/api/v1")
app.include_router(feedback.router,      prefix="/api/v1")

# ── AWS Lambda Handler ────────────────────────────────────────────────────────
handler = Mangum(app, lifespan="off")
