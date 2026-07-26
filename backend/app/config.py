from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    # ── AWS ─────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"

    # ── Bedrock ──────────────────────────────────────────
    BEDROCK_MODEL_ID: str = "amazon.nova-pro-v1:0"

    # ── Pinecone ─────────────────────────────────────────
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "aarogya-index"

    # ── DynamoDB ─────────────────────────────────────────
    DYNAMODB_SESSIONS_TABLE: str = "aarogya-sessions"
    DYNAMODB_PROFILES_TABLE: str = "aarogya-profiles"

    # ── S3 ───────────────────────────────────────────────
    S3_BUCKET_NAME: str = "aarogya-uploads"

    # ── Google Places ────────────────────────────────────
    GOOGLE_PLACES_API_KEY: str = ""

    # ── App ──────────────────────────────────────────────
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def is_local(self) -> bool:
        """Returns True if using a real IAM key (starts with AKIA)."""
        return self.AWS_ACCESS_KEY_ID.startswith("AKIA")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


# Singleton — import this everywhere
settings = Settings()
