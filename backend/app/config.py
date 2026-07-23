"""Application configuration — loads all env vars via Pydantic BaseSettings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── AWS ─────────────────────────────────────────────────────────────────────
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"

    # ── Bedrock ─────────────────────────────────────────────────────────────────
    bedrock_model_id: str = "amazon.nova-pro-v1:0"

    # ── Pinecone ────────────────────────────────────────────────────────────────
    pinecone_api_key: str = ""
    pinecone_index_name: str = "aarogya-index"

    # ── DynamoDB ────────────────────────────────────────────────────────────────
    dynamodb_sessions_table: str = "aarogya-sessions"
    dynamodb_profiles_table: str = "aarogya-profiles"

    # ── S3 ──────────────────────────────────────────────────────────────────────
    s3_bucket_name: str = "aarogya-uploads"

    # ── Google Places ───────────────────────────────────────────────────────────
    google_places_api_key: str = ""

    # ── App ─────────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
